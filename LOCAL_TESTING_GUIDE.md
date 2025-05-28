# Local Testing Guide for Crawl4AI MCP Server

This guide helps you test the MCP server locally without Docker before deploying to Railway.

## Prerequisites

- Python 3.12 or higher
- An OpenAI API key
- A Supabase project with the required table

## Setup Steps

### 1. Install Dependencies

```bash
# Install the project dependencies
pip install -e .

# Or install dependencies directly
pip install crawl4ai==0.6.2 fastmcp>=2.5.0 supabase==2.15.1 openai==1.71.0 python-dotenv>=1.1.0 uvicorn==0.32.1 fastapi==0.115.6 beautifulsoup4 requests
```

### 2. Set Up Environment Variables

Create a `.env` file in the project root with the following variables:

```bash
# Required: OpenAI API key for embeddings
OPENAI_API_KEY=your_openai_api_key_here

# Required: Supabase configuration
SUPABASE_URL=your_supabase_project_url_here
SUPABASE_SERVICE_KEY=your_supabase_service_key_here

# Optional: Model choice for contextual embeddings (if not set, will use basic embeddings)
MODEL_CHOICE=gpt-4o-mini

# Optional: Port for local server (defaults to 11235)
PORT=11235

# Optional: Host for local server (defaults to 0.0.0.0)
HOST=0.0.0.0
```

### 3. Set Up Supabase Database

Make sure your Supabase project has the required table. You can find the SQL schema in the `mcp-crawl4ai-rag/crawled_pages.sql` file.

### 4. Run the Server Locally

```bash
# Navigate to the src directory and run the server
cd src
python crawl4ai_mcp.py
```

The server will start on `http://localhost:11235` (or the port you specified).

## Testing the MCP Tools

### Available Tools

The server provides 4 main MCP tools:
1. **crawl_single_page** - Crawl and store content from a single webpage
2. **smart_crawl_url** - Intelligently crawl based on URL type (sitemap, txt file, or webpage)
3. **get_available_sources** - Get list of all crawled sources/domains
4. **perform_rag_query** - Search the stored content using RAG

### Testing Methods

#### Method 1: Using MCP Session (Recommended)

1. **Get Session ID**:
   ```bash
   curl -X HEAD http://localhost:11235/mcp/ -v
   ```
   Look for the `mcp-session-id` header in the response.

2. **Test Single Page Crawl**:
   ```bash
   curl -X POST http://localhost:11235/mcp/ \
     -H "Content-Type: application/json" \
     -H "Accept: application/json, text/event-stream" \
     -H "mcp-session-id: YOUR_SESSION_ID_HERE" \
     -d '{
       "jsonrpc": "2.0",
       "id": 1,
       "method": "tools/call",
       "params": {
         "tool_name": "crawl_single_page",
         "tool_args": {
           "url": "https://example.com"
         }
       }
     }'
   ```

3. **Test Smart Crawl**:
   ```bash
   curl -X POST http://localhost:11235/mcp/ \
     -H "Content-Type: application/json" \
     -H "Accept: application/json, text/event-stream" \
     -H "mcp-session-id: YOUR_SESSION_ID_HERE" \
     -d '{
       "jsonrpc": "2.0",
       "id": 2,
       "method": "tools/call",
       "params": {
         "tool_name": "smart_crawl_url",
         "tool_args": {
           "url": "https://example.com",
           "max_depth": 2,
           "max_concurrent": 5
         }
       }
     }'
   ```

4. **Test Get Available Sources**:
   ```bash
   curl -X POST http://localhost:11235/mcp/ \
     -H "Content-Type: application/json" \
     -H "Accept: application/json, text/event-stream" \
     -H "mcp-session-id: YOUR_SESSION_ID_HERE" \
     -d '{
       "jsonrpc": "2.0",
       "id": 3,
       "method": "tools/call",
       "params": {
         "tool_name": "get_available_sources",
         "tool_args": {}
       }
     }'
   ```

5. **Test RAG Query**:
   ```bash
   curl -X POST http://localhost:11235/mcp/ \
     -H "Content-Type: application/json" \
     -H "Accept: application/json, text/event-stream" \
     -H "mcp-session-id: YOUR_SESSION_ID_HERE" \
     -d '{
       "jsonrpc": "2.0",
       "id": 4,
       "method": "tools/call",
       "params": {
         "tool_name": "perform_rag_query",
         "tool_args": {
           "query": "What is this website about?",
           "match_count": 3
         }
       }
     }'
   ```

#### Method 2: Using Python Test Script

Create a test script to validate all functions work correctly:

```python
# test_mcp_tools.py
import asyncio
import json
from src.crawl4ai_mcp import mcp, Crawl4AIContext
from src.utils import get_supabase_client
from crawl4ai import AsyncWebCrawler, BrowserConfig

async def test_tools():
    # Create test context
    browser_config = BrowserConfig(headless=True, verbose=False)
    crawler = AsyncWebCrawler(config=browser_config)
    await crawler.__aenter__()
    
    supabase_client = get_supabase_client()
    
    context = Crawl4AIContext(
        crawler=crawler,
        supabase_client=supabase_client
    )
    
    # Mock context for tools
    class MockContext:
        def __init__(self, lifespan_context):
            self.request_context = type('', (), {})()
            self.request_context.lifespan_context = lifespan_context
    
    ctx = MockContext(context)
    
    try:
        # Test crawl_single_page
        print("Testing crawl_single_page...")
        result = await crawl_single_page(ctx, "https://example.com")
        print(f"Result: {result[:200]}...")
        
        # Test get_available_sources
        print("\nTesting get_available_sources...")
        sources = await get_available_sources(ctx)
        print(f"Sources: {sources}")
        
        # Test perform_rag_query
        print("\nTesting perform_rag_query...")
        query_result = await perform_rag_query(ctx, "example", match_count=2)
        print(f"Query result: {query_result[:200]}...")
        
    finally:
        await crawler.__aexit__(None, None, None)

if __name__ == "__main__":
    asyncio.run(test_tools())
```

### Common Issues and Solutions

1. **Port Already in Use**: Change the PORT in your .env file to a different value (e.g., 11236)

2. **OpenAI API Errors**: Make sure your OPENAI_API_KEY is valid and has credits

3. **Supabase Connection Errors**: Verify your SUPABASE_URL and SUPABASE_SERVICE_KEY are correct

4. **Browser Installation**: If crawl4ai has issues, you might need to install browser dependencies:
   ```bash
   playwright install --with-deps
   ```

5. **Memory Issues**: For large crawls, reduce `max_concurrent` parameter

### Health Check

You can verify the server is running by accessing the health endpoint:
```bash
curl http://localhost:11235/health
```

Should return: `healthy%`

## Next Steps

Once all tools work correctly locally:
1. Commit your changes
2. Deploy to Railway
3. The Docker setup on Railway will use the same code but in a containerized environment 