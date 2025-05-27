# Crawl4AI MCP Server - Railway Deployment

A Model Context Protocol (MCP) server for web crawling and RAG (Retrieval-Augmented Generation) using Crawl4AI, deployed on Railway and connected to Supabase.

## Features

- **Smart Web Crawling**: Automatically detects and handles different URL types (sitemaps, text files, regular webpages)
- **RAG Integration**: Store crawled content in Supabase with vector embeddings for semantic search
- **MCP Protocol**: Compatible with AI agents and coding assistants like Claude Desktop and Cursor
- **Cloud Deployment**: Optimized for Railway deployment with Supabase database

## MCP Tools Available

1. **crawl_single_page**: Crawl a single webpage and store in Supabase
2. **smart_crawl_url**: Intelligently crawl URLs with depth control and concurrent processing
3. **get_available_sources**: List all crawled sources in the database
4. **perform_rag_query**: Perform semantic search queries on crawled content

## Environment Variables

The following environment variables are required:

- `SUPABASE_URL`: Your Supabase project URL
- `SUPABASE_SERVICE_KEY`: Your Supabase service role key
- `OPENAI_API_KEY`: OpenAI API key for embeddings
- `HOST`: Server host (default: 0.0.0.0)
- `PORT`: Server port (Railway sets this automatically)

## Railway Deployment

This project is configured for deployment on Railway with the following setup:

1. **Dockerfile**: Optimized for Railway with proper environment handling
2. **Environment Variables**: Configured through Railway dashboard
3. **Database**: Connected to Supabase PostgreSQL with vector search capabilities

## Database Schema

The application uses a `crawled_pages` table in Supabase with the following structure:

```sql
CREATE TABLE crawled_pages (
    id SERIAL PRIMARY KEY,
    url TEXT NOT NULL,
    chunk_number INTEGER NOT NULL DEFAULT 1,
    content TEXT NOT NULL,
    metadata JSONB,
    embedding vector(1536),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

## Local Development

To run locally:

1. Install dependencies: `uv pip install -e .`
2. Set up environment variables in `.env`
3. Run: `uv run src/crawl4ai_mcp.py`

## Usage with MCP Clients

Add to your MCP client configuration:

```json
{
  "mcpServers": {
    "crawl4ai-rag": {
      "command": "uv",
      "args": ["run", "src/crawl4ai_mcp.py"],
      "env": {
        "SUPABASE_URL": "your-supabase-url",
        "SUPABASE_SERVICE_KEY": "your-service-key",
        "OPENAI_API_KEY": "your-openai-key"
      }
    }
  }
}
``` 