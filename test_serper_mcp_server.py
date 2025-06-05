import pytest
import os
from unittest.mock import patch, MagicMock

# Import the FastMCP server instance and any custom exceptions from your server file
from serper_mcp_server import mcp as serper_mcp_server, SerperApiClientError, SERPER_API_KEY_ENV_VAR

# If your server relies on environment variables like SERPER_API_KEY,
# you might want to set it for tests or mock the API responses.
# For this example, we'll assume SERPER_API_KEY is set or we'll mock the underlying API call.

@pytest.fixture
def mcp_server_instance():
    """Provides an instance of the Serper MCP server."""
    # Ensure the API key is set for the test, or mock appropriately.
    # If not set, the _get_resolved_api_key will raise an error.
    # For robust tests, explicitly mock the API call to avoid external dependencies.
    if not os.getenv(SERPER_API_KEY_ENV_VAR):
        os.environ[SERPER_API_KEY_ENV_VAR] = "test_api_key_value" # Provide a dummy key for tests if mocking
    
    # Since tools are now async and use Context, we might need to adjust how the server
    # instance is used or how Client interacts if it expects sync tools directly.
    # However, FastMCP's Client is designed to work with async tools.
    # The main change is that the tool itself is async.
    return serper_mcp_server

@pytest.mark.asyncio
async def test_google_search_tool_success(mcp_server_instance):
    """
    Tests the google_search tool for a successful query.
    This test mocks the underlying 'query_serper_api' to avoid actual API calls.
    """
    expected_response_data = {
        "searchParameters": {"q": "test query", "type": "search"},
        "organic": [{"title": "Test Result", "link": "http://example.com", "snippet": "A test snippet."}]
    }

    # Patch the 'query_serper_api' function within your server's module
    with patch('serper_mcp_server.query_serper_api') as mock_query_serper_api:
        mock_query_serper_api.return_value = expected_response_data
        
        # Mock the context methods if they are called directly in the success path,
        # though for this success test, only query_serper_api is critical.
        # If ctx.info was called before query_serper_api, we'd mock it.
        # For now, we assume ctx.info is called and does not affect the return value.
        mock_ctx = MagicMock()
        mock_ctx.info = MagicMock() # Mock async methods if needed: mock_ctx.info = AsyncMock() for Python 3.8+
        mock_ctx.error = MagicMock()


        # Use the FastMCP client in-memory
        from fastmcp import Client # Import here to ensure server instance is configured
        async with Client(mcp_server_instance) as client:
            # When calling tools that now expect a Context, the FastMCP client
            # should inject it automatically. We don't pass it in call_tool.
            tool_result = await client.call_tool("google_search", {"query": "test query"})

            assert tool_result is not None
            assert len(tool_result) == 1 # Expect one content item
            # The result of call_tool is a list of Content objects.
            # FastMCP by default returns a dictionary from the tool as a JSON string in TextContent.
            # Or, if the tool returns a Pydantic model, it might be handled differently.
            # Assuming it's a dict returned directly from your tool,
            # FastMCP's default behavior might wrap it.
            # Let's assume the tool directly returns the dict and FastMCP passes it through
            # or that the client.call_tool unwraps it appropriately.
            # Based on FastMCP, the raw tool output is often in result[0].data or similar
            # if it's not simple text.
            # For a tool returning a dict, FastMCP client might give it back directly
            # or as a JSON string in result[0].text.
            # Let's assume the client gives us the direct dictionary output if the tool returns a dict.
            # If the tool returns a dict, the client.call_tool should ideally return it as such.
            # The FastMCP documentation snippet `assert result[0].text == "Hello, World!"` implies
            # that if a string is returned, it's in .text.
            # If a dict is returned, it might be directly in the result object or need parsing.
            # Let's assume for now the client returns the dict directly as part of the result structure.
            # The actual structure might be `result[0].data` or similar depending on FastMCP version
            # and how it handles non-string returns.
            # For now, let's assume the tool's direct dictionary output is what we get.
            # This part might need adjustment based on actual Client behavior with dict returns.

            # The `call_tool` method in `fastmcp.Client` returns a list of `Content` objects.
            # If your tool returns a dictionary, `fastmcp` typically serializes it to JSON
            # and places it in the `text` attribute of a `TextContent` object.
            import json
            assert tool_result[0].type == "text"
            response_data = json.loads(tool_result[0].text)

            assert response_data == expected_response_data
            mock_query_serper_api.assert_called_once_with(
                query_text="test query",
                api_key=None, # As it's resolved internally
                search_endpoint="search",
                location=None,
                num_results=None,
                autocorrect=None,
                time_period_filter=None,
                page_number=None
            )

@pytest.mark.asyncio
async def test_google_search_tool_api_error(mcp_server_instance):
    """
    Tests the google_search tool when the Serper API call fails.
    """
    # Patch the 'query_serper_api' function to simulate an API error
    with patch('serper_mcp_server.query_serper_api') as mock_query_serper_api:
        mock_query_serper_api.side_effect = SerperApiClientError("Simulated API error")
        
        # Mock the context methods, especially ctx.error which will be called
        mock_ctx = MagicMock()
        # For Python 3.8+ and async context methods, use AsyncMock
        # from unittest.mock import AsyncMock
        # mock_ctx.error = AsyncMock()
        # For now, assuming MagicMock is sufficient if the actual await doesn't block significantly in test
        mock_ctx.error = MagicMock()
        mock_ctx.info = MagicMock()

        # It's tricky to inject a mock context when using the client.
        # The client will create its own context.
        # Instead, we can patch the Context object creation or its methods globally if needed,
        # or rely on the fact that ctx.error is called and the exception is still raised.
        # For this test, the key is that SerperApiClientError is raised by query_serper_api
        # and then the tool re-raises it (or an encapsulating error).
        # The ctx.error call happens *before* the raise.

        from fastmcp import Client
        from fastmcp.exceptions import ToolError
        async with Client(mcp_server_instance) as client:
            with pytest.raises(ToolError) as exc_info:
                await client.call_tool("google_search", {"query": "test error"})

            # With mask_error_details=True, the specific error message is masked.
            # We expect a generic message from ToolError.
            assert "Error calling tool 'google_search'" in str(exc_info.value)
            # We can also check that the original exception was our SerperApiClientError if needed,
            # but the client won't expose that detail directly in the ToolError message.
            # The server-side log (ctx.error) would have the full detail.
            mock_query_serper_api.assert_called_once_with(
                query_text="test error",
                api_key=None,
                search_endpoint="search",
                location=None,
                num_results=None,
                autocorrect=None,
                time_period_filter=None,
                page_number=None
            )

@pytest.mark.asyncio
async def test_google_search_tool_missing_query(mcp_server_instance):
    """
    Tests the google_search tool when the required 'query' parameter is missing.
    FastMCP should raise an error before the tool code is even called if type hints are used correctly.
    """
    from fastmcp import Client
    from fastmcp.exceptions import ToolError # Changed from ClientError
    async with Client(mcp_server_instance) as client:
        with pytest.raises(ToolError) as exc_info: # Changed from ClientError
            await client.call_tool("google_search", {}) # Missing 'query'

        # The error message will depend on FastMCP's validation
        # Pydantic's error for a missing field 'query' will include these substrings.
        # With mask_error_details=True, the specific Pydantic validation message is masked.
        assert "Error calling tool 'google_search'" in str(exc_info.value)

# --- Tests for news_search tool ---

@pytest.mark.asyncio
async def test_news_search_tool_success(mcp_server_instance):
    """Tests the news_search tool for a successful query."""
    # Correctly indented block starts here
    expected_response_data = {
        "searchParameters": {"q": "latest tech news", "type": "news"},
        "news": [{"title": "Tech News Today", "link": "http://example.com/news", "snippet": "Latest in tech."}]
    }
    with patch('serper_mcp_server.query_serper_api') as mock_query_serper_api:
        mock_query_serper_api.return_value = expected_response_data
        from fastmcp import Client
        async with Client(mcp_server_instance) as client:
            tool_result = await client.call_tool("news_search", {"query": "latest tech news"})
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
                page_number=None
            )

@pytest.mark.asyncio
async def test_news_search_tool_api_error(mcp_server_instance):
    """Tests the news_search tool when the Serper API call fails."""
    # Correctly indented block starts here
    with patch('serper_mcp_server.query_serper_api') as mock_query_serper_api:
        mock_query_serper_api.side_effect = SerperApiClientError("Simulated API error for news")
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
                page_number=None
            )

@pytest.mark.asyncio
async def test_news_search_tool_missing_query(mcp_server_instance):
    """Tests the news_search tool when the required 'query' parameter is missing."""
    # Correctly indented block starts here
    from fastmcp import Client
    from fastmcp.exceptions import ToolError
    async with Client(mcp_server_instance) as client:
        with pytest.raises(ToolError) as exc_info:
            await client.call_tool("news_search", {}) # Missing 'query'
        assert "Error calling tool 'news_search'" in str(exc_info.value)

# --- Tests for scholar_search tool ---

@pytest.mark.asyncio
async def test_scholar_search_tool_success(mcp_server_instance):
    """Tests the scholar_search tool for a successful query."""
    expected_response_data = {
        "searchParameters": {"q": "quantum entanglement", "type": "scholar"},
        "organic": [{"title": "Quantum Entanglement Study", "link": "http://example.com/scholar", "snippet": "A study on quantum."}]
    }
    with patch('serper_mcp_server.query_serper_api') as mock_query_serper_api:
        mock_query_serper_api.return_value = expected_response_data
        from fastmcp import Client
        async with Client(mcp_server_instance) as client:
            tool_result = await client.call_tool("scholar_search", {"query": "quantum entanglement"})
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
                page_number=None
                # Note: scholar_search in serper_mcp_server.py does not take 'location' or 'autocorrect'
            )

@pytest.mark.asyncio
async def test_scholar_search_tool_api_error(mcp_server_instance):
    """Tests the scholar_search tool when the Serper API call fails."""
    with patch('serper_mcp_server.query_serper_api') as mock_query_serper_api:
        mock_query_serper_api.side_effect = SerperApiClientError("Simulated API error for scholar")
        from fastmcp import Client
        from fastmcp.exceptions import ToolError
        async with Client(mcp_server_instance) as client:
            with pytest.raises(ToolError) as exc_info:
                await client.call_tool("scholar_search", {"query": "test scholar error"})
            assert "Error calling tool 'scholar_search'" in str(exc_info.value)
            mock_query_serper_api.assert_called_once_with(
                query_text="test scholar error",
                api_key=None,
                search_endpoint="scholar",
                num_results=None,
                time_period_filter=None,
                page_number=None
            )

@pytest.mark.asyncio
async def test_scholar_search_tool_missing_query(mcp_server_instance):
    """Tests the scholar_search tool when the required 'query' parameter is missing."""
    from fastmcp import Client
    from fastmcp.exceptions import ToolError
    async with Client(mcp_server_instance) as client:
        with pytest.raises(ToolError) as exc_info:
            await client.call_tool("scholar_search", {}) # Missing 'query'
        assert "Error calling tool 'scholar_search'" in str(exc_info.value)

@pytest.mark.asyncio
async def test_google_search_tool_missing_api_key(mcp_server_instance):
    """
    Tests the google_search tool when the SERPER_API_KEY environment variable is not set.
    This test will not mock query_serper_api to allow the API key check to fail.
    """
    original_api_key = os.environ.pop(SERPER_API_KEY_ENV_VAR, None) # Remove key if it exists

    try:
        from fastmcp import Client
        from fastmcp.exceptions import ToolError
        async with Client(mcp_server_instance) as client:
            with pytest.raises(ToolError) as exc_info:
                # We don't mock query_serper_api here, so the call will proceed
                # until _get_resolved_api_key raises an error.
                await client.call_tool("google_search", {"query": "test no key"})
            
            # Check for the generic error message due to mask_error_details=True
            assert "Error calling tool 'google_search'" in str(exc_info.value)
            # The underlying SerperApiClientError message about the missing key will be logged
            # on the server side by ctx.error but masked from the client's ToolError.
    finally:
        if original_api_key is not None:
            os.environ[SERPER_API_KEY_ENV_VAR] = original_api_key # Restore key

# TODO: Consider testing:
# - All parameters (optional ones included for each tool).
# - Different valid values for parameters (e.g., time_period_filter).
# - Edge cases or invalid parameter types (though FastMCP might catch type errors).
# - More detailed testing of _make_serper_request for various HTTP/network errors (requires more complex mocking).