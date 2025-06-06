import asyncio
import http.client
import json
import os
import logging
import argparse # Added for command-line arguments
from collections import defaultdict, deque
from typing import Optional, Dict, Any, Union, Literal, cast
from datetime import datetime, timedelta

from fastmcp import FastMCP, Context
from fastmcp.server.auth import BearerAuthProvider
from fastmcp.server.auth.providers.bearer import RSAKeyPair
from fastmcp.server.dependencies import get_access_token

# --- Configuration ---
SERPER_GOOGLE_SEARCH_HOST = "google.serper.dev"
SERPER_SCRAPE_HOST = "scrape.serper.dev"
SERPER_API_KEY_ENV_VAR = "SERPER_API_KEY"

# Security configuration
MAX_REQUESTS_PER_MINUTE = int(os.getenv("MAX_REQUESTS_PER_MINUTE", "60"))
MAX_QUERY_LENGTH = int(os.getenv("MAX_QUERY_LENGTH", "500"))
ALLOWED_ENDPOINTS = {"search", "news", "scholar", "scrape"}

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("serper_mcp_security.log"), logging.StreamHandler()],
)
security_logger = logging.getLogger("serper_mcp_security")


# --- Rate Limiting ---
class RateLimiter:
    """Simple in-memory rate limiter"""

    def __init__(
        self, max_requests: int = MAX_REQUESTS_PER_MINUTE, window_minutes: int = 1
    ):
        self.max_requests = max_requests
        self.window_minutes = window_minutes
        self.requests: defaultdict[str, deque[datetime]] = defaultdict(deque)

    def is_allowed(self, client_id: str) -> bool:
        now = datetime.utcnow()
        window_start = now - timedelta(minutes=self.window_minutes)

        # Clean old requests
        client_requests = self.requests[client_id]
        while client_requests and client_requests[0] < window_start:
            client_requests.popleft()

        if len(client_requests) >= self.max_requests:
            return False

        client_requests.append(now)
        return True


rate_limiter = RateLimiter()


# --- Input Validation ---
def validate_query_input(query: str, endpoint: str) -> None:
    """Validate user input for security"""
    if not query or not query.strip():
        raise ValueError("Query cannot be empty")

    if len(query) > MAX_QUERY_LENGTH:
        raise ValueError(
            f"Query too long. Maximum {MAX_QUERY_LENGTH} characters allowed"
        )

    if endpoint not in ALLOWED_ENDPOINTS:
        raise ValueError(f"Invalid endpoint. Allowed: {', '.join(ALLOWED_ENDPOINTS)}")

    # Basic injection prevention
    suspicious_patterns = ["<script", "javascript:", "vbscript:", "onload=", "onerror="]
    query_lower = query.lower()
    for pattern in suspicious_patterns:
        if pattern in query_lower:
            raise ValueError("Query contains potentially malicious content")


# --- Custom Exception ---
class SerperApiClientError(Exception):
    """Custom exception for Serper API client errors."""

    pass


class SecurityError(Exception):
    """Custom exception for security-related errors."""

    pass


# --- Private Helper Functions ---
def _get_resolved_api_key(api_key: Optional[str]) -> str:
    """Resolves the API key from argument or environment variable."""
    resolved_key = api_key if api_key is not None else os.getenv(SERPER_API_KEY_ENV_VAR)
    if not resolved_key:
        raise SerperApiClientError(
            f"Serper API key is missing. Please provide it as an argument or set the '{SERPER_API_KEY_ENV_VAR}' environment variable."
        )
    return resolved_key


def _make_serper_request(
    host: str,
    path: str,
    payload: Dict[str, Any],
    api_key: Optional[str] = None,
    client_id: str = "anonymous",
) -> Dict[str, Any]:
    """
    Makes a POST request to a Serper API endpoint with security logging.
    """
    resolved_api_key = _get_resolved_api_key(api_key)

    security_logger.info(
        f"API request from client {client_id} to {host}{path} "
        f"with query length {len(str(payload.get('q', '')))}"
    )

    headers = {
        "X-API-KEY": resolved_api_key,
        "Content-Type": "application/json",
        "User-Agent": "SerperMCP/1.0-secure",
    }

    conn: Optional[http.client.HTTPSConnection] = None
    try:
        conn = http.client.HTTPSConnection(host, timeout=30)
        conn.request("POST", path, json.dumps(payload), headers)
        res = conn.getresponse()
        response_data_bytes = res.read()
    except http.client.HTTPException as e:
        security_logger.error(f"HTTP client error for client {client_id}: {e}")
        raise SerperApiClientError(
            f"HTTP client error during API request to {host}{path}: {e}"
        )
    except ConnectionError as e:
        security_logger.error(f"Network connection error for client {client_id}: {e}")
        raise SerperApiClientError(f"Network connection error to {host}{path}: {e}")
    except Exception as e:
        security_logger.error(f"Unexpected error for client {client_id}: {e}")
        raise SerperApiClientError(
            f"An unexpected error occurred during API request to {host}{path}: {e}"
        )
    finally:
        if conn:
            conn.close()

    try:
        response_data_str = response_data_bytes.decode("utf-8")
    except UnicodeDecodeError as e:
        security_logger.error(f"Unicode decode error for client {client_id}: {e}")
        raise SerperApiClientError(
            f"Failed to decode API response from {host}{path} (not UTF-8): {e}"
        )

    if not (200 <= res.status < 300):
        security_logger.warning(
            f"API error {res.status} for client {client_id} to {host}{path}"
        )
        error_message = (
            f"API request to {host}{path} failed with status {res.status}: {res.reason}. "
            f"Response: {response_data_str[:500]}"
        )
        raise SerperApiClientError(error_message)

    try:
        return json.loads(response_data_str)
    except json.JSONDecodeError as e:
        security_logger.error(f"JSON decode error for client {client_id}: {e}")
        raise SerperApiClientError(
            f"Failed to decode JSON response from {host}{path}: {e}. Response: {response_data_str[:500]}"
        )


# --- Public API Functions ---
def query_serper_api(
    query_text: str,
    api_key: Optional[str] = None,
    search_endpoint: str = "search",
    location: Optional[str] = None,
    num_results: Optional[int] = None,
    autocorrect: Optional[bool] = None,
    time_period_filter: Optional[str] = None,
    page_number: Optional[int] = None,
    client_id: str = "anonymous",
) -> Dict[str, Any]:
    """
    Queries the Serper.dev Search API with security validation.
    """
    # Validate inputs
    validate_query_input(query_text, search_endpoint)

    # Validate optional parameters
    if num_results is not None and (num_results < 1 or num_results > 100):
        raise ValueError("num_results must be between 1 and 100")

    if page_number is not None and (page_number < 1 or page_number > 10):
        raise ValueError("page_number must be between 1 and 10")

    payload: Dict[str, Union[str, int, bool]] = {"q": query_text}
    if location is not None:
        payload["location"] = location
    if num_results is not None:
        payload["num"] = num_results
    payload["autocorrect"] = False if autocorrect is None else autocorrect

    if time_period_filter is not None:
        payload["tbs"] = time_period_filter
    if page_number is not None:
        payload["page"] = page_number

    return _make_serper_request(
        host=SERPER_GOOGLE_SEARCH_HOST,
        path=f"/{search_endpoint}",
        payload=payload,
        api_key=api_key,
        client_id=client_id,
    )


def scrape_serper_url(
    url_to_scrape: str,
    api_key: Optional[str] = None,
    include_markdown: bool = True,
    client_id: str = "anonymous",
) -> Dict[str, Any]:
    """
    Scrapes a webpage using the Serper.dev Scrape API with security validation.
    """
    # Basic URL validation
    if not url_to_scrape or not url_to_scrape.strip():
        raise ValueError("URL cannot be empty")

    if not (
        url_to_scrape.startswith("http://") or url_to_scrape.startswith("https://")
    ):
        raise ValueError("URL must start with http:// or https://")

    if len(url_to_scrape) > 2000:
        raise ValueError("URL too long")

    payload: Dict[str, Union[str, bool]] = {
        "url": url_to_scrape,
        "includeMarkdown": include_markdown,
    }

    return _make_serper_request(
        host=SERPER_SCRAPE_HOST,
        path="/",
        payload=payload,
        api_key=api_key,
        client_id=client_id,
    )


# --- Authentication Setup ---
def setup_authentication() -> Optional[BearerAuthProvider]:
    """Setup authentication based on environment configuration"""
    auth_mode = os.getenv("MCP_AUTH_MODE", "none")

    if auth_mode == "none":
        security_logger.warning(
            "Running without authentication - NOT RECOMMENDED for production"
        )
        return None

    elif auth_mode == "bearer_dev":
        security_logger.info("Setting up development bearer authentication")
        key_pair = RSAKeyPair.generate()

        access_token = key_pair.create_token(audience="serper-mcp-server")
        print(f"\n🔑 Development Access Token:\n{access_token}\n")

        return BearerAuthProvider(
            public_key=key_pair.public_key, audience="serper-mcp-server"
        )

    elif auth_mode == "bearer_prod":
        security_logger.info("Setting up production bearer authentication")

        jwks_uri = os.getenv("JWKS_URI")
        public_key_pem = os.getenv("PUBLIC_KEY_PEM")

        if jwks_uri:
            return BearerAuthProvider(
                jwks_uri=jwks_uri,
                issuer=os.getenv("TOKEN_ISSUER"),
                audience="serper-mcp-server",
            )
        elif public_key_pem:
            return BearerAuthProvider(
                public_key=public_key_pem,
                issuer=os.getenv("TOKEN_ISSUER"),
                audience="serper-mcp-server",
            )
        else:
            raise SecurityError(
                "Production bearer auth requires either JWKS_URI or PUBLIC_KEY_PEM environment variable"
            )

    else:
        raise SecurityError(f"Unknown auth mode: {auth_mode}")


# --- FastMCP Server Definition ---
auth_provider = setup_authentication()

mcp: FastMCP = FastMCP(
    name="SecureSerperDevMCPServer",
    instructions="""This is a secure Serper.dev MCP server with authentication and rate limiting.
It provides tools to interact with Serper.dev's Google Search, Google News, and Google Scholar APIs.
Authentication is required and all requests are logged for security auditing.
Rate limits apply to prevent abuse.""",
    auth=auth_provider,
    mask_error_details=True,
)


# --- Security Middleware ---
async def check_permissions_and_rate_limit(ctx: Context, required_scope: str) -> str:
    """Check authentication, permissions, and rate limits"""
    client_id = "anonymous"

    if auth_provider:
        try:
            access_token = get_access_token()
            if access_token is None:
                raise SecurityError("No access token provided")

            client_id = access_token.client_id or "unknown"

            if required_scope not in access_token.scopes:
                security_logger.warning(
                    f"Access denied for client {client_id}: missing scope {required_scope}"
                )
                raise SecurityError(f"Access denied: {required_scope} scope required")
            security_logger.info(
                f"Authenticated request from client {client_id} with scopes {access_token.scopes}"
            )
        except Exception as e:
            security_logger.error(f"Authentication error: {e}")
            raise SecurityError("Authentication failed")
    if not rate_limiter.is_allowed(client_id):
        security_logger.warning(f"Rate limit exceeded for client {client_id}")
        raise SecurityError("Rate limit exceeded. Please try again later.")
    return client_id


# --- MCP Tool Definitions ---
@mcp.tool()
async def google_search(
    ctx: Context,
    query: str,
    location: Optional[str] = None,
    num_results: Optional[int] = None,
    autocorrect: Optional[bool] = None,
    time_period_filter: Optional[str] = None,
    page_number: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Performs a secure web search using Google (via Serper.dev).
    Requires 'search:read' scope and is subject to rate limiting.
    """
    try:
        client_id = await check_permissions_and_rate_limit(ctx, "search:read")

        await ctx.info(
            f"Secure google_search from client {client_id}: '{query[:50]}...'"
        )

        return query_serper_api(
            query_text=query,
            api_key=None,
            search_endpoint="search",
            location=location,
            num_results=num_results,
            autocorrect=autocorrect,
            time_period_filter=time_period_filter,
            page_number=page_number,
            client_id=client_id,
        )
    except (SecurityError, ValueError) as e:
        await ctx.error(f"Security/validation error in google_search: {e}")
        raise
    except SerperApiClientError as e:
        await ctx.error(
            f"Serper API error in google_search for query '{query[:50]}...': {e}"
        )
        raise
    except Exception as e:
        await ctx.error(f"Unexpected error in google_search: {e}")
        if not isinstance(e, (SerperApiClientError, SecurityError)):
            raise SerperApiClientError(
                f"An unexpected error occurred in google_search tool: {e}"
            ) from e
        raise


@mcp.tool()
async def news_search(
    ctx: Context,
    query: str,
    location: Optional[str] = None,
    num_results: Optional[int] = None,
    autocorrect: Optional[bool] = None,
    time_period_filter: Optional[str] = None,
    page_number: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Securely fetches news articles using Google News.
    Requires 'news:read' scope and is subject to rate limiting.
    """
    try:
        client_id = await check_permissions_and_rate_limit(ctx, "news:read")

        await ctx.info(f"Secure news_search from client {client_id}: '{query[:50]}...'")

        return query_serper_api(
            query_text=query,
            api_key=None,
            search_endpoint="news",
            location=location,
            num_results=num_results,
            autocorrect=autocorrect,
            time_period_filter=time_period_filter,
            page_number=page_number,
            client_id=client_id,
        )
    except (SecurityError, ValueError) as e:
        await ctx.error(f"Security/validation error in news_search: {e}")
        raise
    except SerperApiClientError as e:
        await ctx.error(
            f"Serper API error in news_search for query '{query[:50]}...': {e}"
        )
        raise
    except Exception as e:
        await ctx.error(f"Unexpected error in news_search: {e}")
        if not isinstance(e, (SerperApiClientError, SecurityError)):
            raise SerperApiClientError(
                f"An unexpected error occurred in news_search tool: {e}"
            ) from e
        raise


@mcp.tool()
async def scholar_search(
    ctx: Context,
    query: str,
    num_results: Optional[int] = None,
    time_period_filter: Optional[str] = None,
    page_number: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Securely fetches academic articles using Google Scholar.
    Requires 'scholar:read' scope and is subject to rate limiting.
    """
    try:
        client_id = await check_permissions_and_rate_limit(ctx, "scholar:read")

        await ctx.info(
            f"Secure scholar_search from client {client_id}: '{query[:50]}...'"
        )

        return query_serper_api(
            query_text=query,
            api_key=None,
            search_endpoint="scholar",
            num_results=num_results,
            time_period_filter=time_period_filter,
            page_number=page_number,
            client_id=client_id,
        )
    except (SecurityError, ValueError) as e:
        await ctx.error(f"Security/validation error in scholar_search: {e}")
        raise
    except SerperApiClientError as e:
        await ctx.error(
            f"Serper API error in scholar_search for query '{query[:50]}...': {e}"
        )
        raise
    except Exception as e:
        await ctx.error(f"Unexpected error in scholar_search: {e}")
        if not isinstance(e, (SerperApiClientError, SecurityError)):
            raise SerperApiClientError(
                f"An unexpected error occurred in scholar_search tool: {e}"
            ) from e
        raise

@mcp.tool()
async def scrape_url(
    ctx: Context,
    url: str,
) -> str:
    """
    Securely fetches and extracts the Markdown content from a given URL.
    Requires 'scrape:read' scope and is subject to rate limiting.
    """
    try:
        client_id = await check_permissions_and_rate_limit(ctx, "scrape:read")

        await ctx.info(f"Secure scrape_url from client {client_id}: '{url[:100]}...'")

        # The scrape_serper_url function handles the actual API call and its own validation
        response_data = scrape_serper_url(
            url_to_scrape=url,
            api_key=None,  # Ensures environment variable is used
            include_markdown=True,
            client_id=client_id,
        )

        # Per the requirement, we only return the 'markdown' field.
        markdown_content = response_data.get("markdown", "")
        return markdown_content

    except (SecurityError, ValueError) as e:
        await ctx.error(f"Security/validation error in scrape_url: {e}")
        raise
    except SerperApiClientError as e:
        await ctx.error(f"Serper API error in scrape_url for url '{url[:100]}...': {e}")
        raise
    except Exception as e:
        await ctx.error(f"Unexpected error in scrape_url: {e}")
        if not isinstance(e, (SerperApiClientError, SecurityError)):
            raise SerperApiClientError(
                f"An unexpected error occurred in scrape_url tool: {e}"
            ) from e
        raise

async def print_available_tools():
    """Helper async function to print available tools."""
    tools_dict = await mcp.get_tools()
    print(f"Available tools: {[tool_name for tool_name in tools_dict.keys()]}")


if __name__ == "__main__":
    print("Initializing Secure SerperDevMCPServer...", flush=True)

    api_key_present = os.getenv(SERPER_API_KEY_ENV_VAR)
    if not api_key_present:
        security_logger.error(
            f"CRITICAL: {SERPER_API_KEY_ENV_VAR} environment variable is not set"
        )
        print(f"ERROR: The '{SERPER_API_KEY_ENV_VAR}' environment variable is not set.", flush=True)
        exit(1)
    else:
        security_logger.info("API key configuration verified")
        print(f"✓ {SERPER_API_KEY_ENV_VAR} environment variable is configured", flush=True)

    # Print security configuration
    auth_mode = os.getenv("MCP_AUTH_MODE", "none")
    print(f"Security Mode: {auth_mode}", flush=True)
    print(f"Rate Limit: {MAX_REQUESTS_PER_MINUTE} requests/minute", flush=True)
    print(f"Max Query Length: {MAX_QUERY_LENGTH} characters", flush=True)

    print("Fetching available tools...", flush=True)
    asyncio.run(print_available_tools())

    parser = argparse.ArgumentParser(
        description="Runs the SecureSerperDevMCPServer with authentication and rate limiting, allowing interaction with Serper.dev API services via MCP.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--transport",
        type=str,
        choices=["stdio", "streamable-http", "sse"],
        help=(
            "MCP server transport type.\n"
            "Determines how the server communicates with clients.\n"
            "Options:\n"
            "  stdio: Uses standard input/output (default if not specified and MCP_SERVER_TRANSPORT is not set).\n"
            "  streamable-http: Uses HTTP for web-based clients.\n"
            "  sse: Uses Server-Sent Events (legacy HTTP).\n"
            "This argument overrides the MCP_SERVER_TRANSPORT environment variable."
        ),
    )
    args = parser.parse_args()

    server_host = os.getenv("MCP_SERVER_HOST", "0.0.0.0")
    server_port_str = os.getenv("MCP_SERVER_PORT", "8000")
    try:
        server_port = int(server_port_str)
    except ValueError:
        print(
            f"Warning: Invalid MCP_SERVER_PORT value '{server_port_str}'. Defaulting to 8000.",
            flush=True
        )
        server_port = 8000

    # Determine transport type: CLI arg > env var > default "stdio"
    if args.transport:
        raw_transport_type = args.transport
    else:
        raw_transport_type = os.getenv("MCP_SERVER_TRANSPORT", "stdio") # Default to stdio

    allowed_transports = {"stdio", "streamable-http", "sse"}
    if raw_transport_type not in allowed_transports:
        print(
            f"Warning: Invalid MCP_SERVER_TRANSPORT value '{raw_transport_type}'. Defaulting to 'stdio'.",
            flush=True
        )
        transport_type = cast(Literal["stdio", "streamable-http", "sse"], "stdio")
    else:
        transport_type = cast(Literal["stdio", "streamable-http", "sse"], raw_transport_type)

    print(f"Starting secure server with {transport_type.upper()} transport...", flush=True)
    
    try:
        if transport_type != "stdio":
            print(f"Listening on http://{server_host}:{server_port}", flush=True)
            print("Press Ctrl+C to stop the server.", flush=True)
            mcp.run(transport=transport_type, port=server_port, host=server_host)  # type: ignore
        else:
            print("Using STDIO transport.", flush=True)
            print("Press Ctrl+C to stop the server.", flush=True)
            mcp.run(transport=transport_type)  # host and port are not applicable for stdio
    except KeyboardInterrupt:
        security_logger.info("Server shutdown requested by user")
        print("\nServer shutdown requested by user.", flush=True)
    except Exception as e:
        security_logger.error(f"Failed to start server: {e}")
        print(f"Failed to start server: {e}", flush=True)
