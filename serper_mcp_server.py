import asyncio
import http.client
import json
import os
from typing import Optional, Dict, Any, Union

from fastmcp import FastMCP, Context

# --- Constants ---
SERPER_GOOGLE_SEARCH_HOST = "google.serper.dev"
SERPER_SCRAPE_HOST = "scrape.serper.dev"
SERPER_API_KEY_ENV_VAR = "SERPER_API_KEY"


# --- Custom Exception ---
class SerperApiClientError(Exception):
    """Custom exception for Serper API client errors."""

    pass


# --- Private Helper Function ---
def _get_resolved_api_key(api_key: Optional[str]) -> str:
    """Resolves the API key from argument or environment variable."""
    resolved_key = api_key if api_key is not None else os.getenv(SERPER_API_KEY_ENV_VAR)
    if not resolved_key:
        raise SerperApiClientError(
            f"API key not provided and {SERPER_API_KEY_ENV_VAR} environment variable is not set."
        )
    return resolved_key


def _make_serper_request(
    host: str, path: str, payload: Dict[str, Any], api_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Makes a POST request to a Serper API endpoint.

    Args:
        host: The API host (e.g., "google.serper.dev").
        path: The API path (e.g., "/search" or "/").
        payload: The JSON payload for the request.
        api_key: The Serper API key. If None, uses SERPER_API_KEY_ENV_VAR.

    Returns:
        A dictionary representing the parsed JSON response.

    Raises:
        SerperApiClientError: For API key issues, network errors,
                              non-2xx responses, or JSON decoding failures.
    """
    resolved_api_key = _get_resolved_api_key(api_key)

    headers = {"X-API-KEY": resolved_api_key, "Content-Type": "application/json"}

    conn: Optional[http.client.HTTPSConnection] = None
    try:
        conn = http.client.HTTPSConnection(host)
        conn.request("POST", path, json.dumps(payload), headers)
        res = conn.getresponse()
        response_data_bytes = res.read()
    except http.client.HTTPException as e:
        raise SerperApiClientError(
            f"HTTP client error during API request to {host}{path}: {e}"
        )
    except ConnectionError as e:
        raise SerperApiClientError(f"Network connection error to {host}{path}: {e}")
    except (
        Exception
    ) as e:  # Catching a broader set of potential issues during the request
        raise SerperApiClientError(
            f"An unexpected error occurred during API request to {host}{path}: {e}"
        )
    finally:
        if conn:
            conn.close()

    try:
        response_data_str = response_data_bytes.decode("utf-8")
    except UnicodeDecodeError as e:
        raise SerperApiClientError(
            f"Failed to decode API response from {host}{path} (not UTF-8): {e}"
        )

    if not (200 <= res.status < 300):
        error_message = (
            f"API request to {host}{path} failed with status {res.status}: {res.reason}. "
            f"Response: {response_data_str[:500]}"  # Limit response preview in error
        )
        raise SerperApiClientError(error_message)

    try:
        return json.loads(response_data_str)
    except json.JSONDecodeError as e:
        raise SerperApiClientError(
            f"Failed to decode JSON response from {host}{path}: {e}. Response: {response_data_str[:500]}"
        )


# --- Public API Functions (from user provided code) ---
def query_serper_api(
    query_text: str,
    api_key: Optional[str] = None,
    search_endpoint: str = "search",
    location: Optional[str] = None,
    num_results: Optional[int] = None,
    autocorrect: Optional[bool] = None,
    time_period_filter: Optional[str] = None,
    page_number: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Queries the Serper.dev Search API (google.serper.dev for /search, /news, /scholar).
    """
    if search_endpoint not in ["search", "news", "scholar"]:
        raise SerperApiClientError(
            f"Invalid search_endpoint: '{search_endpoint}'. Must be 'search', 'news', or 'scholar'."
        )

    payload: Dict[str, Union[str, int, bool]] = {"q": query_text}
    if location is not None:
        payload["location"] = location
    if num_results is not None:
        payload["num"] = num_results
    # Default autocorrect to False if not specified, otherwise use the provided value.
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
    )


def scrape_serper_url(
    url_to_scrape: str, api_key: Optional[str] = None, include_markdown: bool = True
) -> Dict[str, Any]:
    """
    Scrapes a webpage using the Serper.dev Scrape API (scrape.serper.dev).
    """
    payload: Dict[str, Union[str, bool]] = {
        "url": url_to_scrape,
        "includeMarkdown": include_markdown,
    }

    return _make_serper_request(
        host=SERPER_SCRAPE_HOST, path="/", payload=payload, api_key=api_key
    )


# --- FastMCP Server Definition ---
mcp: FastMCP = FastMCP(
    name="SerperDevMCPServer",
    instructions="""This server provides tools to interact with Serper.dev's Google Search, Google News, and Google Scholar APIs.
It relies on the SERPER_API_KEY environment variable being set on the server machine for authentication with Serper.dev.
Each tool performs a single query. For multiple distinct queries, call the respective tool multiple times.
Tool annotations like 'readOnlyHint': true, 'idempotentHint': true, 'openWorldHint': true generally apply to these search tools.""",
    mask_error_details=True,  # Mask internal error details from clients
)

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
    Performs a web search using Google (via Serper.dev).
    This tool queries the standard Google search.
    It relies on the SERPER_API_KEY environment variable for authentication.
    This tool is read-only, generally idempotent (results may change over time due to web updates), and interacts with the open web.

    Args:
        query: The search term or question.
        location: The location for the search (e.g., "United States", "London, United Kingdom").
        num_results: Number of results to return (e.g., 10, 20, default is usually 10).
        autocorrect: Whether to enable or disable query autocorrection. Serper's default for this client is False if not specified.
        time_period_filter: Time-based search filter (e.g., "qdr:h" for past hour, "qdr:d" for past day, "qdr:w" for past week). Corresponds to the 'tbs' parameter.
        page_number: The page number of results to fetch (e.g., 1, 2).

    Returns:
        A dictionary representing the parsed JSON response from the Serper API.
        In case of an error from the Serper API, a SerperApiClientError will be raised.
    """
    try:
        await ctx.info(
            f"google_search called with query: '{query}', location: {location}, num_results: {num_results}, autocorrect: {autocorrect}, time_period_filter: {time_period_filter}, page_number: {page_number}"
        )
        return query_serper_api(
            query_text=query,
            api_key=None,  # Ensures environment variable SERPER_API_KEY is used
            search_endpoint="search",
            location=location,
            num_results=num_results,
            autocorrect=autocorrect,
            time_period_filter=time_period_filter,
            page_number=page_number,
        )
    except SerperApiClientError as e:
        await ctx.error(f"Serper API error in google_search for query '{query}': {e}")
        raise
    except Exception as e:
        await ctx.error(f"Unexpected error in google_search for query '{query}': {e}")
        # Re-raise as SerperApiClientError to ensure consistent error type from this layer if not already one
        if not isinstance(e, SerperApiClientError):
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
    Fetches news articles using Google News.
    This tool queries the Google News service.
    It relies on the SERPER_API_KEY environment variable for authentication.
    This tool is read-only, generally idempotent (news results change frequently), and interacts with the open web.

    Args:
        query: The news search term (e.g., "latest AI advancements", "tech earnings").
        location: The location for the news search (e.g., "United States").
        num_results: Number of news articles to return.
        autocorrect: Whether to enable or disable query autocorrection.
        time_period_filter: Time-based search filter (e.g., "qdr:h1" for past hour, "qdr:d1" for past day).
        page_number: The page number of news results to fetch.

    Returns:
        A dictionary representing the parsed JSON response from the Serper API, typically including a 'news' key.
        In case of an error from the Serper API, a SerperApiClientError will be raised.
    """
    try:
        await ctx.info(
            f"news_search called with query: '{query}', location: {location}, num_results: {num_results}, autocorrect: {autocorrect}, time_period_filter: {time_period_filter}, page_number: {page_number}"
        )
        return query_serper_api(
            query_text=query,
            api_key=None,  # Ensures environment variable SERPER_API_KEY is used
            search_endpoint="news",
            location=location,
            num_results=num_results,
            autocorrect=autocorrect,
            time_period_filter=time_period_filter,
            page_number=page_number,
        )
    except SerperApiClientError as e:
        await ctx.error(f"Serper API error in news_search for query '{query}': {e}")
        raise
    except Exception as e:
        await ctx.error(f"Unexpected error in news_search for query '{query}': {e}")
        if not isinstance(e, SerperApiClientError):
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
    Fetches academic/scholar articles using Google Scholar (via Serper.dev).
    This tool queries the Google Scholar service.
    It relies on the SERPER_API_KEY environment variable for authentication.
    This tool is read-only, generally idempotent (results may change over time), and interacts with the open web.

    Args:
        query: The scholar search term (e.g., "quantum computing algorithms", "machine learning in healthcare").
        num_results: Number of scholar articles to return.
        time_period_filter: Time-based search filter for scholar articles (e.g., "as_ylo=2020" for articles from 2020 onwards). Corresponds to 'tbs'.
        page_number: The page number of scholar results to fetch.

    Returns:
        A dictionary representing the parsed JSON response from the Serper API, typically including an 'organic' key.
        In case of an error from the Serper API, a SerperApiClientError will be raised.
    """
    try:
        await ctx.info(
            f"scholar_search called with query: '{query}', num_results: {num_results}, time_period_filter: {time_period_filter}, page_number: {page_number}"
        )
        return query_serper_api(
            query_text=query,
            api_key=None,  # Ensures environment variable SERPER_API_KEY is used
            search_endpoint="scholar",
            num_results=num_results,
            time_period_filter=time_period_filter,
            page_number=page_number,
        )
    except SerperApiClientError as e:
        await ctx.error(f"Serper API error in scholar_search for query '{query}': {e}")
        raise
    except Exception as e:
        await ctx.error(f"Unexpected error in scholar_search for query '{query}': {e}")
        if not isinstance(e, SerperApiClientError):
            raise SerperApiClientError(
                f"An unexpected error occurred in scholar_search tool: {e}"
            ) from e
        raise


async def print_available_tools():
    """Helper async function to print available tools."""
    # Correctly get tools using the async method
    tools_dict = await mcp.get_tools()
    print(f"Available tools: {[tool_name for tool_name in tools_dict.keys()]}")


if __name__ == "__main__":
    print("Initializing SerperDevMCPServer...")

    # Check for API key and print status
    api_key_present = os.getenv(SERPER_API_KEY_ENV_VAR)
    if not api_key_present:
        print(
            f"WARNING: The '{SERPER_API_KEY_ENV_VAR}' environment variable is not set. Serper API calls will likely fail."
        )
        print(
            "Please set it in your environment or in a .env file (if dotenv is used)."
        )
    else:
        print(f"The '{SERPER_API_KEY_ENV_VAR}' environment variable is set.")

    print("Fetching available tools...")
    asyncio.run(print_available_tools())

    server_host = os.getenv("MCP_SERVER_HOST", "0.0.0.0")
    server_port_str = os.getenv("MCP_SERVER_PORT", "8000")
    try:
        server_port = int(server_port_str)
    except ValueError:
        print(
            f"Warning: Invalid MCP_SERVER_PORT value '{server_port_str}'. Defaulting to 8000."
        )
        server_port = 8000

    raw_transport_type = os.getenv("MCP_SERVER_TRANSPORT", "sse")

    allowed_transports = {"stdio", "streamable-http", "sse"}
    if raw_transport_type not in allowed_transports:
        print(
            f"Warning: Invalid MCP_SERVER_TRANSPORT value '{raw_transport_type}'. Defaulting to 'sse'."
        )
        transport_type = "sse"
    else:
        transport_type = raw_transport_type  # type: ignore

    print(f"Attempting to start server with {transport_type.upper()} transport...")
    if transport_type != "stdio":
        print(f"Listening on http://{server_host}:{server_port}")
    else:
        print("Using STDIO transport.")
    print("Press Ctrl+C to stop the server.")

    try:
        mcp.run(transport=transport_type, port=server_port, host=server_host)  # type: ignore
    except KeyboardInterrupt:
        print("\nServer shutdown requested by user.")
    except Exception as e:
        print(f"Failed to start server: {e}")
