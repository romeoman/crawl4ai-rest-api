#!/usr/bin/env python3
"""
Test script for Crawl4AI MCP Server tools
"""
import asyncio
import json
import sys
import os
from pathlib import Path

# Add src directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from crawl4ai_mcp import crawl_single_page, smart_crawl_url, get_available_sources, perform_rag_query, Crawl4AIContext
from utils import get_supabase_client
from crawl4ai import AsyncWebCrawler, BrowserConfig

class MockContext:
    """Mock context for testing MCP tools."""
    def __init__(self, lifespan_context):
        self.request_context = type('', (), {})()
        self.request_context.lifespan_context = lifespan_context

async def test_tools():
    """Test all MCP tools."""
    print("🧪 Testing Crawl4AI MCP Server tools\n")
    
    # Check environment variables
    required_vars = ["OPENAI_API_KEY", "SUPABASE_URL", "SUPABASE_SERVICE_KEY"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print(f"❌ Missing required environment variables: {', '.join(missing_vars)}")
        print("Please check your .env file.")
        return False
    
    print("✅ Environment variables loaded")
    
    # Create test context
    try:
        print("🔧 Setting up test context...")
        browser_config = BrowserConfig(headless=True, verbose=False)
        crawler = AsyncWebCrawler(config=browser_config)
        await crawler.__aenter__()
        
        supabase_client = get_supabase_client()
        print("✅ Supabase client connected")
        
        context = Crawl4AIContext(
            crawler=crawler,
            supabase_client=supabase_client
        )
        
        ctx = MockContext(context)
        
        # Test URLs
        test_url = "https://example.com"
        
        print(f"\n🌐 Testing with URL: {test_url}")
        
        # Test 1: crawl_single_page
        print("\n1️⃣ Testing crawl_single_page...")
        try:
            result = await crawl_single_page(ctx, test_url)
            result_json = json.loads(result)
            if result_json.get("success"):
                print(f"✅ Single page crawl successful")
                print(f"   Chunks stored: {result_json.get('chunks_stored', 0)}")
                print(f"   Content length: {result_json.get('content_length', 0)}")
            else:
                print(f"❌ Single page crawl failed: {result_json.get('error', 'Unknown error')}")
                return False
        except Exception as e:
            print(f"❌ Exception in crawl_single_page: {e}")
            return False
        
        # Test 2: get_available_sources
        print("\n2️⃣ Testing get_available_sources...")
        try:
            sources_result = await get_available_sources(ctx)
            sources_json = json.loads(sources_result)
            if sources_json.get("success"):
                print(f"✅ Get sources successful")
                print(f"   Available sources: {sources_json.get('sources', [])}")
                print(f"   Source count: {sources_json.get('count', 0)}")
            else:
                print(f"❌ Get sources failed: {sources_json.get('error', 'Unknown error')}")
                return False
        except Exception as e:
            print(f"❌ Exception in get_available_sources: {e}")
            return False
        
        # Test 3: perform_rag_query
        print("\n3️⃣ Testing perform_rag_query...")
        try:
            query_result = await perform_rag_query(ctx, "example domain", match_count=2)
            query_json = json.loads(query_result)
            if query_json.get("success"):
                print(f"✅ RAG query successful")
                print(f"   Results found: {query_json.get('count', 0)}")
                if query_json.get('results'):
                    for i, result in enumerate(query_json['results'][:2]):
                        print(f"   Result {i+1}: {result.get('url', 'No URL')}")
                        print(f"   Similarity: {result.get('similarity', 'N/A')}")
            else:
                print(f"❌ RAG query failed: {query_json.get('error', 'Unknown error')}")
                return False
        except Exception as e:
            print(f"❌ Exception in perform_rag_query: {e}")
            return False
        
        # Test 4: smart_crawl_url (optional - takes longer)
        test_smart_crawl = input("\n4️⃣ Test smart_crawl_url? This takes longer (y/N): ").strip().lower()
        if test_smart_crawl == 'y':
            print("Testing smart_crawl_url...")
            try:
                smart_result = await smart_crawl_url(ctx, test_url, max_depth=1, max_concurrent=3)
                smart_json = json.loads(smart_result)
                if smart_json.get("success"):
                    print(f"✅ Smart crawl successful")
                    print(f"   Crawl type: {smart_json.get('crawl_type', 'Unknown')}")
                    print(f"   Pages crawled: {smart_json.get('pages_crawled', 0)}")
                    print(f"   Chunks stored: {smart_json.get('chunks_stored', 0)}")
                else:
                    print(f"❌ Smart crawl failed: {smart_json.get('error', 'Unknown error')}")
                    return False
            except Exception as e:
                print(f"❌ Exception in smart_crawl_url: {e}")
                return False
        else:
            print("⏭️  Skipping smart_crawl_url test")
        
        print("\n🎉 All tests completed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Setup failed: {e}")
        return False
    finally:
        # Clean up
        try:
            await crawler.__aexit__(None, None, None)
            print("🧹 Cleanup completed")
        except:
            pass

def main():
    """Main test function."""
    print("🔍 Crawl4AI MCP Server Tool Tests")
    print("=" * 40)
    
    # Load environment variables
    from dotenv import load_dotenv
    load_dotenv()
    
    # Run tests
    success = asyncio.run(test_tools())
    
    if success:
        print("\n✅ All tests passed! Your local setup is working correctly.")
        print("\nYou can now:")
        print("1. Start the server: cd src && python crawl4ai_mcp.py")
        print("2. Test with curl commands from LOCAL_TESTING_GUIDE.md")
        print("3. Deploy to Railway when ready")
    else:
        print("\n❌ Some tests failed. Please check the errors above.")
    
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 