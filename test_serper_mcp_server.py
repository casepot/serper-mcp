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

        # Use the FastMCP client in-memory
        from fastmcp import Client # Import here to ensure server instance is configured
        async with Client(mcp_server_instance) as client:
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

        from fastmcp import Client
        from fastmcp.exceptions import ToolError # Changed from ClientError
        async with Client(mcp_server_instance) as client:
            with pytest.raises(ToolError) as exc_info: # Changed from ClientError
                await client.call_tool("google_search", {"query": "test error"})

            assert "Simulated API error" in str(exc_info.value)
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
        assert "query" in str(exc_info.value) and "Missing required argument" in str(exc_info.value)

# TODO: Add similar tests for 'news_search' and 'scholar_search' tools.
# Consider testing:
# - All parameters (optional ones included).
# - Different valid values for parameters (e.g., time_period_filter).
# - Edge cases or invalid parameter types (though FastMCP might catch type errors).
# - Cases where SERPER_API_KEY is not set (if not mocking query_serper_api).