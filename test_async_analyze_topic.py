#!/usr/bin/env python3
"""
Test script for the optimized async analyze_topic function.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add src directory to path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from serper_mcp_server import analyze_topic
from fastmcp import Context

class MockContext:
    """Mock context for testing."""
    
    async def info(self, message: str):
        print(f"[INFO] {message}")
    
    async def warning(self, message: str):
        print(f"[WARNING] {message}")
    
    async def error(self, message: str):
        print(f"[ERROR] {message}")

async def test_async_analyze_topic():
    """Test the optimized async analyze_topic function."""
    
    # Check environment variables
    if not os.getenv("SERPER_API_KEY"):
        print("❌ SERPER_API_KEY not set")
        return
    
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ OPENAI_API_KEY not set")
        return
    
    print("✅ API keys found")
    print("🚀 Testing optimized async analyze_topic function...")
    
    # Create mock context
    ctx = MockContext()
    
    # Minimal test parameters to stay under timeout
    try:
        result = await analyze_topic(
            ctx=ctx,
            query="Python programming",
            search_depth=1,
            max_urls_per_query=1,  # Very minimal to test quickly
            search_types=["search"],
            chunk_size=200,
            chunk_overlap=20,
            max_entities_per_chunk=3,
            allowed_entity_types=["Technology", "Concept"]
        )
        
        print("🎉 Test completed successfully!")
        print(f"URLs scraped: {result['processing_stats']['urls_scraped']}")
        print(f"Chunks processed: {result['processing_stats']['chunks_processed']}")
        print(f"Entities extracted: {result['processing_stats']['entities_extracted']}")
        print(f"Relationships found: {result['processing_stats']['relationships_found']}")
        print(f"Central entities: {len(result['key_insights']['central_entities'])}")
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_async_analyze_topic())
    sys.exit(0 if success else 1)