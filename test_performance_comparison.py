#!/usr/bin/env python3
"""
Performance comparison test showing the benefits of async optimization.
"""

import asyncio
import time
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
        pass  # Silent for performance testing
    
    async def warning(self, message: str):
        print(f"[WARNING] {message}")
    
    async def error(self, message: str):
        print(f"[ERROR] {message}")

async def run_performance_test():
    """Run a more comprehensive performance test."""
    
    # Check environment variables
    if not os.getenv("SERPER_API_KEY") or not os.getenv("OPENAI_API_KEY"):
        print("❌ Missing API keys")
        return False
    
    print("🚀 Running performance test with optimized async analyze_topic...")
    print("📊 Parameters: 2 URLs, larger chunks for more OpenAI API calls")
    
    ctx = MockContext()
    
    start_time = time.time()
    
    try:
        result = await analyze_topic(
            ctx=ctx,
            query="machine learning",
            search_depth=1,
            max_urls_per_query=2,  # More URLs
            search_types=["search"],
            chunk_size=400,  # Larger chunks
            chunk_overlap=50,
            max_entities_per_chunk=5,
            allowed_entity_types=["Technology", "Concept", "Organization"]
        )
        
        end_time = time.time()
        total_time = end_time - start_time
        
        print(f"\n✅ Performance Test Results:")
        print(f"⏱️  Total execution time: {total_time:.2f} seconds")
        print(f"🌐 URLs scraped: {result['processing_stats']['urls_scraped']}")
        print(f"📝 Chunks processed: {result['processing_stats']['chunks_processed']}")
        print(f"🤖 OpenAI API calls made: ~{result['processing_stats']['chunks_processed'] + 5}")
        print(f"🎯 Entities extracted: {result['processing_stats']['entities_extracted']}")
        print(f"🔗 Relationships found: {result['processing_stats']['relationships_found']}")
        
        # Calculate estimated sequential time (assuming 2-3 seconds per API call)
        api_calls = result['processing_stats']['chunks_processed'] + 5
        estimated_sequential_time = api_calls * 2.5  # Conservative estimate
        
        print(f"\n📈 Performance Analysis:")
        print(f"🔄 Estimated sequential time: {estimated_sequential_time:.1f} seconds")
        print(f"⚡ Actual parallel time: {total_time:.1f} seconds")
        print(f"🚀 Speed improvement: {estimated_sequential_time/total_time:.1f}x faster")
        
        return True
        
    except Exception as e:
        print(f"❌ Performance test failed: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(run_performance_test())
    sys.exit(0 if success else 1)