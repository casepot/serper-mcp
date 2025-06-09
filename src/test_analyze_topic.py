import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from serper_mcp_server import mcp as serper_mcp_server


@pytest.fixture
def mcp_server_instance():
    """Provides an instance of the Serper MCP server."""
    return serper_mcp_server


@pytest.mark.asyncio
async def test_analyze_topic_smoke_test(mcp_server_instance):
    """
    A basic smoke test for the analyze_topic tool.
    This test mocks the underlying API calls to ensure the tool can be called without errors.
    """
    with patch("serper_mcp_server.super_search", new_callable=AsyncMock) as mock_super_search, \
         patch("serper_mcp_server.scrape_url", new_callable=AsyncMock) as mock_scrape_url, \
         patch("serper_mcp_server.openai_client") as mock_openai_client:

        # Mock the return values of the dependencies
        mock_super_search.return_value = {
            "aggregated_results": {
                "search": {
                    "test query": {
                        "organic": [{"link": "http://example.com"}]
                    }
                }
            }
        }
        mock_scrape_url.return_value = "This is a test document."
        mock_openai_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="Parsed relationship: Entity1 -> related_to -> Entity2 [strength: 0.8]"))]
        )

        from fastmcp import Client

        async with Client(mcp_server_instance) as client:
            tool_result = await client.call_tool(
                "analyze_topic", {"query": "test query"}
            )

            assert tool_result is not None
            assert len(tool_result) == 1
            assert tool_result[0].type == "text"
            
            import json
            response_data = json.loads(tool_result[0].text)

            assert "query" in response_data
            assert "processing_stats" in response_data
            assert "key_insights" in response_data
            assert "knowledge_graph" in response_data
            assert "sources" in response_data