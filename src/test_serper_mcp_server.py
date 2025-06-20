import pytest
import os
import subprocess
import sys
from unittest.mock import patch, MagicMock

from serper_mcp_server import (
    mcp as serper_mcp_server,
    SerperApiClientError,
    SERPER_API_KEY_ENV_VAR,
)


@pytest.fixture
def mcp_server_instance():
    """Provides an instance of the Serper MCP server."""
    if not os.getenv(SERPER_API_KEY_ENV_VAR):
        os.environ[SERPER_API_KEY_ENV_VAR] = "test_api_key_value"
    return serper_mcp_server


@pytest.mark.asyncio
async def test_google_search_tool_success(mcp_server_instance):
    """
    Tests the google_search tool for a successful query.
    This test mocks the underlying 'query_serper_api' to avoid actual API calls.
    """
    expected_response_data = {
        "searchParameters": {"q": "test query", "type": "search"},
        "organic": [
            {
                "title": "Test Result",
                "link": "http://example.com",
                "snippet": "A test snippet.",
            }
        ],
    }

    # Patch the 'query_serper_api' function within your server's module
    with patch("serper_mcp_server.query_serper_api") as mock_query_serper_api:
        mock_query_serper_api.return_value = expected_response_data

        mock_ctx = MagicMock()
        mock_ctx.info = (
            MagicMock()
        )  # Mock async methods if needed: mock_ctx.info = AsyncMock() for Python 3.8+
        mock_ctx.error = MagicMock()

        # Use the FastMCP client in-memory
        from fastmcp import (
            Client,
        )  # Import here to ensure server instance is configured

        async with Client(mcp_server_instance) as client:
            # When calling tools that now expect a Context, the FastMCP client
            # should inject it automatically. We don't pass it in call_tool.
            tool_result = await client.call_tool(
                "google_search", {"query": "test query"}
            )

            assert tool_result is not None
            assert len(tool_result) == 1  # Expect one content item

            # The `call_tool` method in `fastmcp.Client` returns a list of `Content` objects.
            # If a tool returns a dictionary, `fastmcp` typically serializes it to JSON
            # and places it in the `text` attribute of a `TextContent` object.
            import json

            assert tool_result[0].type == "text"
            response_data = json.loads(tool_result[0].text)

            assert response_data == expected_response_data
            mock_query_serper_api.assert_called_once_with(
                query_text="test query",
                api_key=None,  # As it's resolved internally
                search_endpoint="search",
                location=None,
                num_results=None,
                autocorrect=None,
                time_period_filter=None,
                page_number=None,
            )


@pytest.mark.asyncio
async def test_google_search_tool_api_error(mcp_server_instance):
    """
    Tests the google_search tool when the Serper API call fails.
    """
    with patch("serper_mcp_server.query_serper_api") as mock_query_serper_api:
        mock_query_serper_api.side_effect = SerperApiClientError("Simulated API error")
        mock_ctx = MagicMock()
        mock_ctx.error = MagicMock()
        mock_ctx.info = MagicMock()

        from fastmcp import Client
        from fastmcp.exceptions import ToolError

        async with Client(mcp_server_instance) as client:
            with pytest.raises(ToolError) as exc_info:
                await client.call_tool("google_search", {"query": "test error"})

            assert "Error calling tool 'google_search'" in str(exc_info.value)
            mock_query_serper_api.assert_called_once_with(
                query_text="test error",
                api_key=None,
                search_endpoint="search",
                location=None,
                num_results=None,
                autocorrect=None,
                time_period_filter=None,
                page_number=None,
            )


@pytest.mark.asyncio
async def test_google_search_tool_missing_query(mcp_server_instance):
    """ """
    from fastmcp import Client
    from fastmcp.exceptions import ToolError

    async with Client(mcp_server_instance) as client:
        with pytest.raises(ToolError) as exc_info:
            await client.call_tool("google_search", {})
        assert "Error calling tool 'google_search'" in str(exc_info.value)


@pytest.mark.asyncio
async def test_news_search_tool_success(mcp_server_instance):
    """Tests the news_search tool for a successful query."""
    expected_response_data = {
        "searchParameters": {"q": "latest tech news", "type": "news"},
        "news": [
            {
                "title": "Tech News Today",
                "link": "http://example.com/news",
                "snippet": "Latest in tech.",
            }
        ],
    }
    with patch("serper_mcp_server.query_serper_api") as mock_query_serper_api:
        mock_query_serper_api.return_value = expected_response_data
        from fastmcp import Client

        async with Client(mcp_server_instance) as client:
            tool_result = await client.call_tool(
                "news_search", {"query": "latest tech news"}
            )
            assert tool_result is not None
            assert len(tool_result) == 1
            import json

            assert tool_result[0].type == "text"
            response_data = json.loads(tool_result[0].text)
            assert response_data == expected_response_data
            mock_query_serper_api.assert_called_once_with(
                query_text="latest tech news",
                api_key=None,
                search_endpoint="news",
                location=None,
                num_results=None,
                autocorrect=None,
                time_period_filter=None,
                page_number=None,
            )


@pytest.mark.asyncio
async def test_news_search_tool_api_error(mcp_server_instance):
    """Tests the news_search tool when the Serper API call fails."""
    with patch("serper_mcp_server.query_serper_api") as mock_query_serper_api:
        mock_query_serper_api.side_effect = SerperApiClientError(
            "Simulated API error for news"
        )
        from fastmcp import Client
        from fastmcp.exceptions import ToolError

        async with Client(mcp_server_instance) as client:
            with pytest.raises(ToolError) as exc_info:
                await client.call_tool("news_search", {"query": "test news error"})
            assert "Error calling tool 'news_search'" in str(exc_info.value)
            mock_query_serper_api.assert_called_once_with(
                query_text="test news error",
                api_key=None,
                search_endpoint="news",
                location=None,
                num_results=None,
                autocorrect=None,
                time_period_filter=None,
                page_number=None,
            )


@pytest.mark.asyncio
async def test_news_search_tool_missing_query(mcp_server_instance):
    """Tests the news_search tool when the required 'query' parameter is missing."""
    from fastmcp import Client
    from fastmcp.exceptions import ToolError

    async with Client(mcp_server_instance) as client:
        with pytest.raises(ToolError) as exc_info:
            await client.call_tool("news_search", {})
        assert "Error calling tool 'news_search'" in str(exc_info.value)


@pytest.mark.asyncio
async def test_scholar_search_tool_success(mcp_server_instance):
    """Tests the scholar_search tool for a successful query."""
    expected_response_data = {
        "searchParameters": {"q": "quantum entanglement", "type": "scholar"},
        "organic": [
            {
                "title": "Quantum Entanglement Study",
                "link": "http://example.com/scholar",
                "snippet": "A study on quantum.",
            }
        ],
    }
    with patch("serper_mcp_server.query_serper_api") as mock_query_serper_api:
        mock_query_serper_api.return_value = expected_response_data
        from fastmcp import Client

        async with Client(mcp_server_instance) as client:
            tool_result = await client.call_tool(
                "scholar_search", {"query": "quantum entanglement"}
            )
            assert tool_result is not None
            assert len(tool_result) == 1
            import json

            assert tool_result[0].type == "text"
            response_data = json.loads(tool_result[0].text)
            assert response_data == expected_response_data
            mock_query_serper_api.assert_called_once_with(
                query_text="quantum entanglement",
                api_key=None,
                search_endpoint="scholar",
                num_results=None,
                time_period_filter=None,
                page_number=None,
            )


@pytest.mark.asyncio
async def test_scholar_search_tool_api_error(mcp_server_instance):
    """Tests the scholar_search tool when the Serper API call fails."""
    with patch("serper_mcp_server.query_serper_api") as mock_query_serper_api:
        mock_query_serper_api.side_effect = SerperApiClientError(
            "Simulated API error for scholar"
        )
        from fastmcp import Client
        from fastmcp.exceptions import ToolError

        async with Client(mcp_server_instance) as client:
            with pytest.raises(ToolError) as exc_info:
                await client.call_tool(
                    "scholar_search", {"query": "test scholar error"}
                )
            assert "Error calling tool 'scholar_search'" in str(exc_info.value)
            mock_query_serper_api.assert_called_once_with(
                query_text="test scholar error",
                api_key=None,
                search_endpoint="scholar",
                num_results=None,
                time_period_filter=None,
                page_number=None,
            )


@pytest.mark.asyncio
async def test_scholar_search_tool_missing_query(mcp_server_instance):
    """Tests the scholar_search tool when the required 'query' parameter is missing."""
    from fastmcp import Client
    from fastmcp.exceptions import ToolError

    async with Client(mcp_server_instance) as client:
        with pytest.raises(ToolError) as exc_info:
            await client.call_tool("scholar_search", {})  # Missing 'query'
        assert "Error calling tool 'scholar_search'" in str(exc_info.value)


@pytest.mark.asyncio
async def test_google_search_tool_missing_api_key(mcp_server_instance, caplog): # Add caplog fixture
    """
    Tests the google_search tool when the SERPER_API_KEY environment variable is not set.
    Checks that the specific error message is logged by FastMCP.
    """
    original_api_key = os.environ.pop(SERPER_API_KEY_ENV_VAR, None)
    try:
        from fastmcp import Client
        from fastmcp.exceptions import ToolError

        # Set log level for the test to capture ERROR messages from FastMCP
        import logging
        caplog.set_level(logging.ERROR, logger="FastMCP.fastmcp.tools.tool_manager")

        async with Client(mcp_server_instance) as client:
            with pytest.raises(ToolError) as exc_info: # We still expect ToolError to be raised
                await client.call_tool("google_search", {"query": "test no key"})
            
            # Assert that the generic ToolError message is present
            assert "Error calling tool 'google_search'" in str(exc_info.value)

            # Assert that the specific underlying error message was logged by FastMCP's tool_manager
            log_messages = [record.message for record in caplog.records]
            expected_log_message_part = (
                f"Error calling tool 'google_search': Serper API key is missing. "
                f"Please provide it as an argument or set the '{SERPER_API_KEY_ENV_VAR}' environment variable."
            )
            assert any(expected_log_message_part in msg for msg in log_messages)

    finally:
        if original_api_key is not None:
            os.environ[SERPER_API_KEY_ENV_VAR] = original_api_key


# --- Tests for command-line argument and environment variable handling ---

# Helper function to run the server script as a subprocess
def run_server_script(script_path, cli_args=None, env_vars=None, timeout=2):
    """
    Runs a server script as a subprocess and returns its output.
    Adds a timeout to prevent tests from hanging indefinitely.
    """
    command = [sys.executable, script_path]
    if cli_args:
        command.extend(cli_args)

    current_env = os.environ.copy()
    if env_vars:
        current_env.update(env_vars)
    
    # Ensure SERPER_API_KEY is set for the subprocess, otherwise server exits early
    if SERPER_API_KEY_ENV_VAR not in current_env:
        current_env[SERPER_API_KEY_ENV_VAR] = "test_api_key_for_startup"

    try:
        process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            env=current_env,
            timeout=timeout,  # Add a timeout
        )
        return process
    except subprocess.TimeoutExpired as e:
        # This is expected for servers that run indefinitely
        return e


@pytest.mark.parametrize(
    "script_name, cli_args, env_vars, expected_transport_msg, expected_listen_msg",
    [
        # serper_mcp_server.py tests
        ("serper_mcp_server.py", [], {}, "Attempting to start server with STDIO transport...", "Using STDIO transport."), # Default
        ("serper_mcp_server.py", ["--transport", "stdio"], {}, "Attempting to start server with STDIO transport...", "Using STDIO transport."),
        ("serper_mcp_server.py", ["--transport", "sse"], {}, "Attempting to start server with SSE transport...", "Listening on http://0.0.0.0:8000"),
        ("serper_mcp_server.py", ["--transport", "streamable-http"], {}, "Attempting to start server with STREAMABLE-HTTP transport...", "Listening on http://0.0.0.0:8000"),
        ("serper_mcp_server.py", [], {"MCP_SERVER_TRANSPORT": "stdio"}, "Attempting to start server with STDIO transport...", "Using STDIO transport."),
        ("serper_mcp_server.py", [], {"MCP_SERVER_TRANSPORT": "sse"}, "Attempting to start server with SSE transport...", "Listening on http://0.0.0.0:8000"),
        ("serper_mcp_server.py", [], {"MCP_SERVER_TRANSPORT": "streamable-http"}, "Attempting to start server with STREAMABLE-HTTP transport...", "Listening on http://0.0.0.0:8000"),
        ("serper_mcp_server.py", ["--transport", "stdio"], {"MCP_SERVER_TRANSPORT": "sse"}, "Attempting to start server with STDIO transport...", "Using STDIO transport."), # CLI overrides ENV
        # serper_mcp_server_secure.py tests
        ("serper_mcp_server_secure.py", [], {}, "Starting secure server with STDIO transport...", "Using STDIO transport."), # Default
        ("serper_mcp_server_secure.py", ["--transport", "stdio"], {}, "Starting secure server with STDIO transport...", "Using STDIO transport."),
        ("serper_mcp_server_secure.py", ["--transport", "sse"], {}, "Starting secure server with SSE transport...", "Listening on http://0.0.0.0:8000"),
        ("serper_mcp_server_secure.py", ["--transport", "streamable-http"], {}, "Starting secure server with STREAMABLE-HTTP transport...", "Listening on http://0.0.0.0:8000"),
        ("serper_mcp_server_secure.py", [], {"MCP_SERVER_TRANSPORT": "stdio"}, "Starting secure server with STDIO transport...", "Using STDIO transport."),
        ("serper_mcp_server_secure.py", [], {"MCP_SERVER_TRANSPORT": "sse"}, "Starting secure server with SSE transport...", "Listening on http://0.0.0.0:8000"),
        ("serper_mcp_server_secure.py", [], {"MCP_SERVER_TRANSPORT": "streamable-http"}, "Starting secure server with STREAMABLE-HTTP transport...", "Listening on http://0.0.0.0:8000"),
        ("serper_mcp_server_secure.py", ["--transport", "stdio"], {"MCP_SERVER_TRANSPORT": "sse"}, "Starting secure server with STDIO transport...", "Using STDIO transport."), # CLI overrides ENV
    ],
)
def test_server_transport_selection(script_name, cli_args, env_vars, expected_transport_msg, expected_listen_msg):
    script_path = os.path.join(os.path.dirname(__file__), script_name)
    result = run_server_script(script_path, cli_args, env_vars)

    output = ""
    if isinstance(result, subprocess.CompletedProcess):
        output = result.stdout + result.stderr
    elif isinstance(result, subprocess.TimeoutExpired):
        output = result.stdout.decode(errors='ignore') if result.stdout else ""
        output += result.stderr.decode(errors='ignore') if result.stderr else ""
    
    # print(f"\n--- Output for {script_name} with args {cli_args} and env {env_vars} ---")
    # print(output)
    # print("--- End Output ---")

    assert expected_transport_msg in output
    if expected_listen_msg: # Not all transports will have a listen message (e.g. stdio)
        assert expected_listen_msg in output

@pytest.mark.parametrize(
    "script_name, cli_args, env_vars, expected_error_msg_part",
    [
        ("serper_mcp_server.py", ["--transport", "invalid_transport"], {}, "invalid choice: 'invalid_transport'"), # Invalid CLI
        ("serper_mcp_server.py", [], {"MCP_SERVER_TRANSPORT": "invalid_env_transport"}, "Warning: Invalid MCP_SERVER_TRANSPORT value 'invalid_env_transport'. Defaulting to 'stdio'."), # Invalid ENV
        ("serper_mcp_server_secure.py", ["--transport", "invalid_transport_secure"], {}, "invalid choice: 'invalid_transport_secure'"), # Invalid CLI secure
        ("serper_mcp_server_secure.py", [], {"MCP_SERVER_TRANSPORT": "invalid_env_transport_secure"}, "Warning: Invalid MCP_SERVER_TRANSPORT value 'invalid_env_transport_secure'. Defaulting to 'stdio'."), # Invalid ENV secure
    ]
)
def test_server_invalid_transport_input(script_name, cli_args, env_vars, expected_error_msg_part):
    script_path = os.path.join(os.path.dirname(__file__), script_name)
    result = run_server_script(script_path, cli_args, env_vars, timeout=1) # Shorter timeout for expected errors

    output = ""
    if isinstance(result, subprocess.CompletedProcess):
        output = result.stdout + result.stderr # Argparse errors go to stderr
    elif isinstance(result, subprocess.TimeoutExpired): # Should not happen for argparse errors
        output = result.stdout.decode(errors='ignore') if result.stdout else ""
        output += result.stderr.decode(errors='ignore') if result.stderr else ""

    # print(f"\n--- Error Output for {script_name} with args {cli_args} and env {env_vars} ---")
    # print(output)
    # print("--- End Error Output ---")
    assert expected_error_msg_part in output


@pytest.mark.asyncio
async def test_scrape_url_tool_success(mcp_server_instance):
    """
    Tests the scrape_url tool for a successful scrape.
    This test mocks the underlying 'scrape_serper_url' to avoid actual API calls.
    """
    # Simulate a raw response with HTML entities and backslash escapes
    raw_markdown_from_api = "## Scraped Content<br>\n\nThis is a \\*test\\* with \\_escapes\\_ and & an ampersand."
    # The expected output after cleaning
    expected_cleaned_markdown = "## Scraped Content<br>\n\nThis is a *test* with _escapes_ and & an ampersand."
    
    full_api_response = {
        "text": "Scraped Content...",
        "markdown": raw_markdown_from_api,
        "metadata": {"title": "Scraped Page"},
        "credits": 1,
    }

    with patch("serper_mcp_server.scrape_serper_url") as mock_scrape_serper_url:
        mock_scrape_serper_url.return_value = full_api_response

        from fastmcp import Client

        async with Client(mcp_server_instance) as client:
            tool_result = await client.call_tool(
                "scrape_url", {"url": "http://example.com/scrape-me"}
            )

            assert tool_result is not None
            assert len(tool_result) == 1
            assert tool_result[0].type == "text"
            # The tool should return the cleaned markdown string
            assert tool_result[0].text == expected_cleaned_markdown

            mock_scrape_serper_url.assert_called_once_with(
                url_to_scrape="http://example.com/scrape-me",
                api_key=None,
                include_markdown=True,
            )


@pytest.mark.asyncio
async def test_scrape_url_tool_api_error(mcp_server_instance):
    """
    Tests the scrape_url tool when the underlying Serper API call fails.
    """
    with patch("serper_mcp_server.scrape_serper_url") as mock_scrape_serper_url:
        mock_scrape_serper_url.side_effect = SerperApiClientError(
            "Simulated scrape API error"
        )

        from fastmcp import Client
        from fastmcp.exceptions import ToolError

        async with Client(mcp_server_instance) as client:
            with pytest.raises(ToolError) as exc_info:
                await client.call_tool(
                    "scrape_url", {"url": "http://example.com/scrape-error"}
                )

            assert "Error calling tool 'scrape_url'" in str(exc_info.value)
            mock_scrape_serper_url.assert_called_once_with(
                url_to_scrape="http://example.com/scrape-error",
                api_key=None,
                include_markdown=True,
            )

@pytest.mark.asyncio
async def test_scrape_url_tool_with_github_url_transformation(mcp_server_instance):
    """
    Tests that the scrape_url tool correctly transforms a GitHub URL
    before calling the underlying scrape function.
    """
    original_github_url = "https://github.com/some-user/some-repo/blob/main/docs/README.md"
    expected_raw_url = "https://raw.githubusercontent.com/some-user/some-repo/main/docs/README.md"
    # Simulate a raw response with HTML entities from a GitHub file
    raw_markdown_from_api = "### Title with & special chars"
    expected_cleaned_markdown = "### Title with & special chars"
    
    full_api_response = {"markdown": raw_markdown_from_api}

    with patch("serper_mcp_server.scrape_serper_url") as mock_scrape_serper_url:
        mock_scrape_serper_url.return_value = full_api_response

        from fastmcp import Client

        async with Client(mcp_server_instance) as client:
            tool_result = await client.call_tool(
                "scrape_url", {"url": original_github_url}
            )

            assert tool_result is not None
            assert len(tool_result) == 1
            assert tool_result[0].type == "text"
            assert tool_result[0].text == expected_cleaned_markdown

            # Verify that the scraper was called with the *transformed* URL
            mock_scrape_serper_url.assert_called_once_with(
                url_to_scrape=expected_raw_url,
                api_key=None,
                include_markdown=True,
            )

# It's better to have a separate test file for the secure server,
# but for this task, I will add them here.

@pytest.fixture
def secure_mcp_server_instance():
    """Provides an instance of the Secure Serper MCP server."""
    from serper_mcp_server_secure import mcp
    from fastmcp.server.auth import BearerAuthProvider
    from fastmcp.server.auth.providers.bearer import RSAKeyPair

    key_pair = RSAKeyPair.generate()
    mock_auth_provider = BearerAuthProvider(
        public_key=key_pair.public_key, audience="serper-mcp-server"
    )
    
    with patch("serper_mcp_server_secure.auth_provider", mock_auth_provider):
        if not os.getenv(SERPER_API_KEY_ENV_VAR):
            os.environ[SERPER_API_KEY_ENV_VAR] = "test_api_key_value"
        yield mcp

@pytest.mark.asyncio
async def test_secure_scrape_url_tool_success(secure_mcp_server_instance):
    """
    Tests the secure scrape_url tool for a successful scrape with valid auth.
    """
    mcp_instance = secure_mcp_server_instance
    expected_markdown = "## Secure Scraped Content"
    full_api_response = {"markdown": expected_markdown}

    with patch("serper_mcp_server_secure.scrape_serper_url") as mock_scrape, \
         patch("serper_mcp_server_secure.get_access_token") as mock_get_token:
        
        from fastmcp.server.dependencies import AccessToken
        mock_get_token.return_value = AccessToken(token="dummy-token", client_id="test-client", scopes=["scrape:read"])
        mock_scrape.return_value = full_api_response

        from fastmcp import Client
        
        async with Client(mcp_instance) as client:
            tool_result = await client.call_tool(
                "scrape_url", {"url": "https://example.com/secure-page"}
            )
            assert tool_result is not None
            assert len(tool_result) == 1
            assert tool_result[0].type == "text"
            assert tool_result[0].text == expected_markdown

        mock_scrape.assert_called_once()
        call_args = mock_scrape.call_args[1]
        assert call_args['url_to_scrape'] == "https://example.com/secure-page"


@pytest.mark.asyncio
async def test_secure_scrape_url_tool_auth_error(secure_mcp_server_instance):
    """
    Tests the secure scrape_url tool for a failure due to missing auth scope.
    """
    mcp_instance = secure_mcp_server_instance
    with patch("serper_mcp_server_secure.scrape_serper_url") as mock_scrape, \
         patch("serper_mcp_server_secure.get_access_token") as mock_get_token:

        from fastmcp.server.dependencies import AccessToken
        # Token is missing the required 'scrape:read' scope
        mock_get_token.return_value = AccessToken(token="dummy-token", client_id="test-client", scopes=["search:read"])

        from fastmcp import Client
        from fastmcp.exceptions import ToolError

        async with Client(mcp_instance) as client:
            with pytest.raises(ToolError) as exc_info:
                await client.call_tool(
                    "scrape_url", {"url": "https://example.com/secure-page"}
                )
            
            assert exc_info.type is ToolError
        
        mock_scrape.assert_not_called()
