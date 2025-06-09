import asyncio
from unittest.mock import MagicMock, AsyncMock
from serper_mcp_server import analyze_topic

async def main():
    # Mock the context object
    ctx = MagicMock()
    ctx.info = AsyncMock()
    ctx.warning = AsyncMock()
    ctx.error = AsyncMock()

    # Call the function directly
    result = await analyze_topic(
        ctx=ctx,
        query="The future of artificial intelligence",
        search_depth=1,
        max_urls_per_query=2,
        search_types=["search", "news"],
    )

    print(result)

if __name__ == "__main__":
    asyncio.run(main())