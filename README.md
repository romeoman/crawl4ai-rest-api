# Crawl4AI REST API - Web Crawling & RAG Service

A powerful REST API for web crawling and RAG (Retrieval-Augmented Generation) using Crawl4AI, deployed on Railway and connected to Supabase.

## Features

- **Smart Web Crawling**: Automatically detects and handles different URL types (sitemaps, text files, regular webpages)
- **URL Freshness Control**: Avoids re-crawling URLs within 30 days (configurable) to prevent duplication
- **RAG Integration**: Store crawled content in Supabase with vector embeddings for semantic search
- **Authentication**: Secure API access with Bearer token authentication
- **Cloud Deployment**: Optimized for Railway deployment with Supabase database

## Quick Start

### Environment Variables

Set the following environment variables in your `.env` file:

```bash
# Required
SUPABASE_URL=your_supabase_project_url
SUPABASE_SERVICE_KEY=your_supabase_service_role_key
OPENAI_API_KEY=your_openai_api_key

# Optional
CRAWL4AI_API_KEY=your_api_key_for_authentication
HOST=0.0.0.0
PORT=8000
```

### Installation & Running

```bash
# Install dependencies
pip install -r requirements.txt

# Run the server
cd src && python rest_api.py
```

The API will be available at `http://localhost:8000` with interactive docs at `http://localhost:8000/docs`.

## Authentication

The API supports Bearer token authentication. Include your API key in the Authorization header:

```bash
Authorization: Bearer your_api_key_here
```

If `CRAWL4AI_API_KEY` is not set, the API runs in open mode (no authentication required).

## API Endpoints

### Health Check

Check if the API is running and healthy.

**Endpoint:** `GET /health`

**curl Example:**
```bash
curl -X GET "http://localhost:8000/health"
```

**TypeScript Example:**
```typescript
interface HealthResponse {
  status: string;
  service: string;
}

const checkHealth = async (): Promise<HealthResponse> => {
  const response = await fetch('http://localhost:8000/health');
  return response.json();
};
```

**Response:**
```json
{
  "status": "healthy",
  "service": "Crawl4AI REST API"
}
```

### Check URL Freshness

Check if a URL was crawled recently and determine if re-crawling is needed.

**Endpoint:** `POST /check-freshness`

**curl Example:**
```bash
curl -X POST "http://localhost:8000/check-freshness" \
  -H "Authorization: Bearer your_api_key" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com",
    "freshness_days": 30
  }'
```

**TypeScript Example:**
```typescript
interface CheckFreshnessRequest {
  url: string;
  freshness_days?: number; // default: 30
}

interface CheckFreshnessResponse {
  success: boolean;
  url: string;
  is_fresh: boolean;
  last_crawled?: string;
  days_since_crawl?: number;
  error?: string;
}

const checkFreshness = async (request: CheckFreshnessRequest): Promise<CheckFreshnessResponse> => {
  const response = await fetch('http://localhost:8000/check-freshness', {
    method: 'POST',
    headers: {
      'Authorization': 'Bearer your_api_key',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(request),
  });
  return response.json();
};
```

### Crawl Single Page

Crawl a single webpage and store the content with embeddings.

**Endpoint:** `POST /crawl/single`

**curl Example:**
```bash
curl -X POST "http://localhost:8000/crawl/single" \
  -H "Authorization: Bearer your_api_key" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com",
    "force_recrawl": false
  }'
```

**TypeScript Example:**
```typescript
interface CrawlSinglePageRequest {
  url: string;
  force_recrawl?: boolean; // default: false
}

interface CrawlSinglePageResponse {
  success: boolean;
  url?: string;
  content_length?: number;
  chunks_stored?: number;
  was_fresh?: boolean;
  last_crawled?: string;
  error?: string;
}

const crawlSinglePage = async (request: CrawlSinglePageRequest): Promise<CrawlSinglePageResponse> => {
  const response = await fetch('http://localhost:8000/crawl/single', {
    method: 'POST',
    headers: {
      'Authorization': 'Bearer your_api_key',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(request),
  });
  return response.json();
};
```

### Smart Crawl

Intelligently crawl URLs with automatic type detection and depth control.

**Endpoint:** `POST /crawl/smart`

**curl Example:**
```bash
curl -X POST "http://localhost:8000/crawl/smart" \
  -H "Authorization: Bearer your_api_key" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com/sitemap.xml",
    "max_depth": 3,
    "max_concurrent": 10,
    "chunk_size": 5000,
    "force_recrawl": false
  }'
```

**TypeScript Example:**
```typescript
interface SmartCrawlRequest {
  url: string;
  max_depth?: number; // default: 3
  max_concurrent?: number; // default: 10
  chunk_size?: number; // default: 5000
  force_recrawl?: boolean; // default: false
}

interface SmartCrawlResponse {
  success: boolean;
  url?: string;
  crawl_type?: string; // "sitemap" | "txt_file" | "webpage"
  pages_crawled?: number;
  chunks_stored?: number;
  skipped_fresh_urls?: number;
  error?: string;
}

const smartCrawl = async (request: SmartCrawlRequest): Promise<SmartCrawlResponse> => {
  const response = await fetch('http://localhost:8000/crawl/smart', {
    method: 'POST',
    headers: {
      'Authorization': 'Bearer your_api_key',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(request),
  });
  return response.json();
};
```

### Get Available Sources

List all available sources (domains) that have been crawled.

**Endpoint:** `GET /sources`

**curl Example:**
```bash
curl -X GET "http://localhost:8000/sources" \
  -H "Authorization: Bearer your_api_key"
```

**TypeScript Example:**
```typescript
interface AvailableSourcesResponse {
  success: boolean;
  sources: string[];
  count?: number;
  error?: string;
}

const getAvailableSources = async (): Promise<AvailableSourcesResponse> => {
  const response = await fetch('http://localhost:8000/sources', {
    headers: {
      'Authorization': 'Bearer your_api_key',
    },
  });
  return response.json();
};
```

### RAG Query

Perform semantic search on crawled content using vector similarity.

**Endpoint:** `POST /query/rag`

**curl Example:**
```bash
curl -X POST "http://localhost:8000/query/rag" \
  -H "Authorization: Bearer your_api_key" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "machine learning algorithms",
    "source": "example.com",
    "match_count": 5
  }'
```

**TypeScript Example:**
```typescript
interface RAGQueryRequest {
  query: string;
  source?: string; // filter by specific domain
  match_count?: number; // default: 5
}

interface RAGQueryResponse {
  success: boolean;
  query?: string;
  source_filter?: string;
  results: Array<{
    url: string;
    content: string;
    metadata: Record<string, any>;
    similarity: number;
  }>;
  count?: number;
  error?: string;
}

const performRAGQuery = async (request: RAGQueryRequest): Promise<RAGQueryResponse> => {
  const response = await fetch('http://localhost:8000/query/rag', {
    method: 'POST',
    headers: {
      'Authorization': 'Bearer your_api_key',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(request),
  });
  return response.json();
};
```

## URL Freshness System

The API implements a smart URL freshness system to avoid unnecessary re-crawling:

- **Default Freshness Period**: 30 days
- **Automatic Detection**: URLs crawled within the freshness period are considered "fresh"
- **Force Recrawl**: Use `force_recrawl: true` to bypass freshness checks
- **Smart Filtering**: Bulk operations automatically filter out fresh URLs

### Freshness Behavior

1. **First Crawl**: URLs never crawled before are always processed
2. **Fresh URLs**: URLs crawled within the freshness period are skipped (unless forced)
3. **Stale URLs**: URLs older than the freshness period are re-crawled
4. **Batch Operations**: Smart crawl automatically filters fresh URLs and reports skip counts

## Database Schema

The application uses a `crawled_pages` table in Supabase:

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

## Error Handling

All endpoints return consistent error responses:

```typescript
interface ErrorResponse {
  success: false;
  error: string;
  // Additional endpoint-specific fields may be included
}
```

Common HTTP status codes:
- `200`: Success
- `401`: Unauthorized (invalid or missing API key)
- `422`: Validation Error (invalid request data)
- `500`: Internal Server Error

## Testing

Run the comprehensive test suite:

```bash
python test_rest_api.py
```

The test script includes:
- Health check
- Authentication testing
- URL freshness checking
- Single page crawling
- Force recrawl functionality
- Smart crawling
- RAG queries
- Source listing

## Deployment

### Railway Deployment

This project is configured for Railway deployment:

1. **Environment Variables**: Set in Railway dashboard
2. **Automatic Builds**: Triggered on Git push
3. **Supabase Integration**: PostgreSQL with vector search

### Local Development

```bash
# Clone the repository
git clone <repository-url>
cd Crawl4ai

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env with your credentials

# Run the server
cd src && python rest_api.py
```

## Features Overview

### Smart Crawling Types

1. **Sitemap Crawling**: Automatically extracts URLs from XML sitemaps
2. **Text File Processing**: Handles .txt files with content extraction
3. **Recursive Web Crawling**: Follows internal links up to specified depth

### Content Processing

- **Smart Chunking**: Respects code blocks and paragraph boundaries
- **Vector Embeddings**: OpenAI embeddings for semantic search
- **Metadata Extraction**: Headers, word counts, and source information
- **Deduplication**: Prevents duplicate content storage

### Performance Features

- **Concurrent Processing**: Configurable concurrent crawling
- **Memory Management**: Adaptive memory usage monitoring
- **Batch Operations**: Efficient database operations
- **Caching**: Browser cache management for optimal performance

## License

MIT License - see LICENSE file for details. 