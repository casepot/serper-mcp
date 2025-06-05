import pytest
import os
from unittest.mock import patch, MagicMock

from serper_mcp_server import mcp as serper_mcp_server, SerperApiClientError, SERPER_API_KEY_ENV_VAR


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
        "organic": [{"title": "Test Result", "link": "http://example.com", "snippet": "A test snippet."}]
    }

    # Patch the 'query_serper_api' function within your server's module
    with patch('serper_mcp_server.query_serper_api') as mock_query_serper_api:
        mock_query_serper_api.return_value = expected_response_data
        
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

            # The `call_tool` method in `fastmcp.Client` returns a list of `Content` objects.
            # If a tool returns a dictionary, `fastmcp` typically serializes it to JSON
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
    with patch('serper_mcp_server.query_serper_api') as mock_query_serper_api:
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
                page_number=None
            )

@pytest.mark.asyncio
async def test_google_search_tool_missing_query(mcp_server_instance):
    """
    """
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
    """
    original_api_key = os.environ.pop(SERPER_API_KEY_ENV_VAR, None)
    try:
        from fastmcp import Client
        from fastmcp.exceptions import ToolError
        async with Client(mcp_server_instance) as client:
            with pytest.raises(ToolError) as exc_info:
                await client.call_tool("google_search", {"query": "test no key"})
            assert "Error calling tool 'google_search'" in str(exc_info.value)
    finally:
        if original_api_key is not None:
            os.environ[SERPER_API_KEY_ENV_VAR] = original_api_key