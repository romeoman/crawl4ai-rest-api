# Quick Local Setup for Crawl4AI MCP Server

Follow these steps to set up and test the MCP server locally without Docker:

## 1. Create Virtual Environment

```bash
# Create a Python virtual environment
python3 -m venv venv

# Activate the virtual environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
# venv\Scripts\activate
```

## 2. Install Dependencies

```bash
# Upgrade pip first
pip install --upgrade pip

# Install the project dependencies
pip install -e .

# Or install dependencies directly if the above fails:
pip install crawl4ai==0.6.2 fastmcp>=2.5.0 supabase==2.15.1 openai==1.71.0 python-dotenv>=1.1.0 uvicorn==0.32.1 fastapi==0.115.6 beautifulsoup4 requests

# Install playwright browsers (this may take a while)
playwright install --with-deps
```

## 3. Set Up Environment Variables

Create a `.env` file in the project root:

```bash
# Create .env file with your credentials
cat > .env << 'EOF'
# Required: OpenAI API key for embeddings
OPENAI_API_KEY=your_openai_api_key_here

# Required: Supabase configuration
SUPABASE_URL=your_supabase_project_url_here
SUPABASE_SERVICE_KEY=your_supabase_service_key_here

# Optional: Model choice for contextual embeddings
MODEL_CHOICE=gpt-4o-mini

# Optional: Port for local server (defaults to 11235)
PORT=11235
EOF
```

**Important**: Replace the placeholder values with your actual API keys!

## 4. Set Up Supabase Database

Make sure your Supabase project has the required table. Run this SQL in your Supabase SQL editor:

```sql
-- Check if the table exists, create if needed
CREATE TABLE IF NOT EXISTS crawled_pages (
    id BIGSERIAL PRIMARY KEY,
    url TEXT NOT NULL,
    chunk_number INTEGER NOT NULL,
    content TEXT NOT NULL,
    metadata JSONB,
    embedding VECTOR(1536),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS crawled_pages_url_idx ON crawled_pages (url);
CREATE INDEX IF NOT EXISTS crawled_pages_embedding_idx ON crawled_pages USING ivfflat (embedding vector_cosine_ops);
```

## 5. Test the Tools (Direct Function Testing)

```bash
# Run the test script to verify all tools work
python test_mcp_tools.py
```

## 6. Start the MCP Server

```bash
# Navigate to src directory and start the server
cd src
python crawl4ai_mcp.py
```

You should see output like:
```
FastMCP version: 2.5.1
Starting MCP server on 0.0.0.0:11235
```

## 7. Test the Server (HTTP/JSON-RPC)

Open a new terminal and test the server:

### Get Session ID
```bash
curl -X HEAD http://localhost:11235/mcp/ -v 2>&1 | grep mcp-session-id
```

### Test Single Page Crawl
```bash
# Replace YOUR_SESSION_ID_HERE with the actual session ID from above
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

### Test Health Endpoint
```bash
curl http://localhost:11235/health
```
Should return: `healthy%`

## Available MCP Tools

1. **crawl_single_page** - Crawl and store a single webpage
2. **smart_crawl_url** - Intelligently crawl based on URL type
3. **get_available_sources** - Get list of crawled sources
4. **perform_rag_query** - Search stored content using RAG

## Troubleshooting

### Common Issues:

1. **Permission denied / externally-managed-environment**: 
   - Make sure you're using a virtual environment (`source venv/bin/activate`)

2. **Playwright browser installation fails**:
   ```bash
   pip install playwright
   playwright install --with-deps
   ```

3. **Supabase connection errors**:
   - Verify your SUPABASE_URL and SUPABASE_SERVICE_KEY in `.env`
   - Make sure the table exists in your Supabase project

4. **OpenAI API errors**:
   - Verify your OPENAI_API_KEY is valid and has credits

5. **Port already in use**:
   - Change PORT in `.env` to a different value (e.g., 11236)

## Deploy to Railway

Once everything works locally:

1. Commit your changes (make sure `.env` is in `.gitignore`)
2. Push to your Railway project
3. Set the environment variables in Railway dashboard
4. Deploy!

The Railway deployment uses Docker, but the same code runs in both environments. 