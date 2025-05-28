"""
REST API server for web crawling with Crawl4AI.

This server provides REST API endpoints to crawl websites using Crawl4AI, automatically detecting
the appropriate crawl method based on URL type (sitemap, txt file, or regular webpage).
"""
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Security, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse, urldefrag
from xml.etree import ElementTree
from dotenv import load_dotenv
from supabase import Client, create_client
from pathlib import Path
from datetime import datetime
import requests
import asyncio
import json
import os
import re
import uvicorn
import sys

# Add the src directory to Python path for imports
current_dir = Path(__file__).resolve().parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode, MemoryAdaptiveDispatcher
from utils import (
    get_supabase_client, add_documents_to_supabase, search_documents,
    check_url_freshness, get_stale_urls, validate_api_key
)

# Load environment variables from the project root .env file
project_root = Path(__file__).resolve().parent.parent
dotenv_path = project_root / '.env'

# Force override of existing environment variables
load_dotenv(dotenv_path, override=True)

# Security
security = HTTPBearer(auto_error=False)

def get_api_key(credentials: HTTPAuthorizationCredentials = Security(security)):
    """
    Dependency to extract and validate API key from Authorization header.
    """
    if credentials is None:
        # Check if API key is required
        if os.getenv("CRAWL4AI_API_KEY"):
            raise HTTPException(
                status_code=401,
                detail="Authorization header required"
            )
        return None
    
    if not validate_api_key(credentials.credentials):
        raise HTTPException(
            status_code=401,
            detail="Invalid API key"
        )
    
    return credentials.credentials

# Create a dataclass for our application context
@dataclass
class Crawl4AIContext:
    """Context for the Crawl4AI REST API server."""
    crawler: AsyncWebCrawler
    supabase_client: Client

# Global context variable
app_context: Optional[Crawl4AIContext] = None

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Manages the Crawl4AI client lifecycle.
    """
    global app_context
    
    # Create browser configuration
    browser_config = BrowserConfig(
        headless=True,
        verbose=False
    )
    
    # Initialize the crawler
    crawler = AsyncWebCrawler(config=browser_config)
    await crawler.__aenter__()
    
    # Initialize Supabase client
    supabase_client = get_supabase_client()
    
    app_context = Crawl4AIContext(
        crawler=crawler,
        supabase_client=supabase_client
    )
    
    try:
        yield
    finally:
        # Clean up the crawler
        await crawler.__aexit__(None, None, None)
        app_context = None

# Create FastAPI instance
app = FastAPI(
    title="Crawl4AI REST API",
    description="Web crawling and RAG query API using Crawl4AI",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # React development server
        "http://localhost:8080",  # Vue development server
        "http://localhost:5173",  # Vite development server
        "https://*.railway.app",  # Railway deployment domains
        "https://*.vercel.app",   # Vercel deployment domains
        "https://*.netlify.app",  # Netlify deployment domains
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=[
        "Accept",
        "Accept-Language", 
        "Content-Language",
        "Content-Type",
        "Authorization",
        "X-API-Key",
        "X-Requested-With",
        "Origin",
        "Referer",
        "User-Agent"
    ],
    expose_headers=["X-Total-Count", "X-Page-Count"],
    max_age=86400,  # Cache preflight requests for 24 hours
)

# Pydantic models for request/response
class CrawlSinglePageRequest(BaseModel):
    url: str
    force_recrawl: bool = False

class CrawlSinglePageResponse(BaseModel):
    success: bool
    url: Optional[str] = None
    content_length: Optional[int] = None
    chunks_stored: Optional[int] = None
    was_fresh: Optional[bool] = None
    last_crawled: Optional[str] = None
    error: Optional[str] = None

class SmartCrawlRequest(BaseModel):
    url: str
    max_depth: int = 3
    max_concurrent: int = 10
    chunk_size: int = 5000
    force_recrawl: bool = False

class SmartCrawlResponse(BaseModel):
    success: bool
    url: Optional[str] = None
    crawl_type: Optional[str] = None
    pages_crawled: Optional[int] = None
    chunks_stored: Optional[int] = None
    skipped_fresh_urls: Optional[int] = None
    error: Optional[str] = None

class RAGQueryRequest(BaseModel):
    query: str
    source: Optional[str] = None
    match_count: int = 5

class RAGQueryResponse(BaseModel):
    success: bool
    query: Optional[str] = None
    source_filter: Optional[str] = None
    results: List[Dict[str, Any]] = []
    count: Optional[int] = None
    error: Optional[str] = None

class AvailableSourcesResponse(BaseModel):
    success: bool
    sources: List[str] = []
    count: Optional[int] = None
    error: Optional[str] = None

# Helper functions (unchanged from original)
def is_sitemap(url: str) -> bool:
    """Check if a URL is a sitemap."""
    return url.endswith('sitemap.xml') or 'sitemap' in urlparse(url).path

def is_txt(url: str) -> bool:
    """Check if a URL is a text file."""
    return url.endswith('.txt')

def parse_sitemap(sitemap_url: str) -> List[str]:
    """Parse a sitemap and extract URLs."""
    resp = requests.get(sitemap_url)
    urls = []

    if resp.status_code == 200:
        try:
            tree = ElementTree.fromstring(resp.content)
            urls = [loc.text for loc in tree.findall('.//{*}loc')]
        except Exception as e:
            print(f"Error parsing sitemap XML: {e}")

    return urls

def smart_chunk_markdown(text: str, chunk_size: int = 5000) -> List[str]:
    """Split text into chunks, respecting code blocks and paragraphs."""
    chunks = []
    start = 0
    text_length = len(text)

    while start < text_length:
        # Calculate end position
        end = start + chunk_size

        # If we're at the end of the text, just take what's left
        if end >= text_length:
            chunks.append(text[start:].strip())
            break

        # Try to find a code block boundary first (```)
        chunk = text[start:end]
        code_block = chunk.rfind('```')
        if code_block != -1 and code_block > chunk_size * 0.3:
            end = start + code_block

        # If no code block, try to break at a paragraph
        elif '\n\n' in chunk:
            # Find the last paragraph break
            last_break = chunk.rfind('\n\n')
            if last_break > chunk_size * 0.3:  # Only break if we're past 30% of chunk_size
                end = start + last_break

        # If no paragraph break, try to break at a sentence
        elif '. ' in chunk:
            # Find the last sentence break
            last_period = chunk.rfind('. ')
            if last_period > chunk_size * 0.3:  # Only break if we're past 30% of chunk_size
                end = start + last_period + 1

        # Extract chunk and clean it up
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        # Move start position for next chunk
        start = end

    return chunks

def extract_section_info(chunk: str) -> Dict[str, Any]:
    """Extracts headers and stats from a chunk."""
    headers = re.findall(r'^(#+)\s+(.+)$', chunk, re.MULTILINE)
    header_str = '; '.join([f'{h[0]} {h[1]}' for h in headers]) if headers else ''

    return {
        "headers": header_str,
        "word_count": len(chunk.split()),
        "char_count": len(chunk)
    }

# REST API Endpoints

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "Crawl4AI REST API"}

@app.get("/playground")
async def playground(request: Request):
    """Simple web interface for testing the API and browsing data."""
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Crawl4AI REST API Playground</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
                   background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; }
            .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
            .header { text-align: center; color: white; margin-bottom: 40px; }
            .header h1 { font-size: 2.5rem; margin-bottom: 10px; }
            .header p { font-size: 1.1rem; opacity: 0.9; }
            .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }
            .card { background: white; border-radius: 12px; padding: 24px; box-shadow: 0 4px 20px rgba(0,0,0,0.1); }
            .card h3 { color: #333; margin-bottom: 16px; font-size: 1.3rem; }
            .endpoint { background: #f8f9fa; border-radius: 8px; padding: 12px; margin: 8px 0; }
            .method { display: inline-block; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 0.8rem; }
            .get { background: #28a745; color: white; }
            .post { background: #007bff; color: white; }
            .endpoint-path { font-family: monospace; color: #495057; margin-left: 8px; }
            .endpoint-desc { font-size: 0.9rem; color: #6c757d; margin-top: 4px; }
            .info-section { background: #e3f2fd; border-left: 4px solid #2196f3; padding: 16px; margin: 16px 0; border-radius: 4px; }
            .warning-section { background: #fff3e0; border-left: 4px solid #ff9800; padding: 16px; margin: 16px 0; border-radius: 4px; }
            .code { background: #f4f4f4; border-radius: 4px; padding: 8px; font-family: monospace; font-size: 0.9rem; }
            .status-indicator { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 8px; }
            .status-healthy { background: #28a745; }
            .status-pending { background: #ffc107; }
            .button { background: #007bff; color: white; border: none; padding: 10px 16px; border-radius: 6px; 
                     cursor: pointer; font-size: 0.9rem; text-decoration: none; display: inline-block; }
            .button:hover { background: #0056b3; }
            .env-vars { font-size: 0.85rem; line-height: 1.6; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🕷️ Crawl4AI REST API Playground</h1>
                <p>Interactive testing interface for the Crawl4AI FastAPI deployment</p>
            </div>
            
            <div class="grid">
                <!-- API Status -->
                <div class="card">
                    <h3><span class="status-indicator status-healthy"></span>API Status</h3>
                    <p><strong>Base URL:</strong> <span class="code">""" + str(request.base_url) + """</span></p>
                    <p><strong>Service:</strong> Crawl4AI REST API</p>
                    <p><strong>Environment:</strong> Railway Production</p>
                    
                    <div class="info-section">
                        <strong>🔑 Authentication Required:</strong><br>
                        Bearer Token: <span class="code">secure-crawl4ai-bearer-token-2024</span>
                    </div>
                </div>
                
                <!-- Available Endpoints -->
                <div class="card">
                    <h3>📡 Available Endpoints</h3>
                    
                    <div class="endpoint">
                        <span class="method get">GET</span>
                        <span class="endpoint-path">/health</span>
                        <div class="endpoint-desc">Check API health status</div>
                    </div>
                    
                    <div class="endpoint">
                        <span class="method post">POST</span>
                        <span class="endpoint-path">/crawl/single</span>
                        <div class="endpoint-desc">Crawl a single webpage</div>
                    </div>
                    
                    <div class="endpoint">
                        <span class="method post">POST</span>
                        <span class="endpoint-path">/crawl/smart</span>
                        <div class="endpoint-desc">Smart multi-page crawling</div>
                    </div>
                    
                    <div class="endpoint">
                        <span class="method post">POST</span>
                        <span class="endpoint-path">/query/rag</span>
                        <div class="endpoint-desc">Query crawled content with RAG</div>
                    </div>
                    
                    <div class="endpoint">
                        <span class="method get">GET</span>
                        <span class="endpoint-path">/sources</span>
                        <div class="endpoint-desc">List all crawled sources</div>
                    </div>
                    
                    <div class="endpoint">
                        <span class="method post">POST</span>
                        <span class="endpoint-path">/check-freshness</span>
                        <div class="endpoint-desc">Check URL freshness status</div>
                    </div>
                </div>
                
                <!-- Quick Test -->
                <div class="card">
                    <h3>🧪 Quick Test</h3>
                    <p>Test the health endpoint:</p>
                    <div class="code">
curl -H "Authorization: Bearer secure-crawl4ai-bearer-token-2024" \\<br>
&nbsp;&nbsp;&nbsp;&nbsp;""" + str(request.base_url) + """health
                    </div>
                    
                    <p style="margin-top: 16px;">Test a simple crawl:</p>
                    <div class="code">
curl -X POST \\<br>
&nbsp;&nbsp;-H "Authorization: Bearer secure-crawl4ai-bearer-token-2024" \\<br>
&nbsp;&nbsp;-H "Content-Type: application/json" \\<br>
&nbsp;&nbsp;-d '{"url": "https://example.com"}' \\<br>
&nbsp;&nbsp;""" + str(request.base_url) + """crawl/single
                    </div>
                </div>
                
                <!-- Database Info -->
                <div class="card">
                    <h3>🗄️ Database Status</h3>
                    <p><strong>Database:</strong> Supabase PostgreSQL</p>
                    <p><strong>Features:</strong> Vector embeddings, RAG queries</p>
                    <p><strong>Freshness Period:</strong> 30 days</p>
                    
                    <div class="warning-section">
                        <strong>⚠️ Current Limitations:</strong><br>
                        • LLM extraction not yet implemented<br>
                        • Database browser not available<br>
                        • Interactive testing limited
                    </div>
                </div>
                
                <!-- Environment -->
                <div class="card">
                    <h3>🔧 Environment Configuration</h3>
                    <div class="env-vars">
                        <strong>Production Settings:</strong><br>
                        • PORT: 8000<br>
                        • FRESHNESS_PERIOD_DAYS: 30<br>
                        • Browser: Chromium (headless)<br>
                        • Chunking: Smart markdown splitting<br>
                        • Authentication: Bearer token required
                    </div>
                </div>
                
                <!-- Resources -->
                <div class="card">
                    <h3>📚 Resources</h3>
                    <p><strong>Documentation:</strong></p>
                    <p>• Check <span class="code">POSTMAN_TESTING_GUIDE.md</span> for detailed API docs</p>
                    <p>• See <span class="code">API_CREDENTIALS.txt</span> for authentication details</p>
                    
                    <p style="margin-top: 12px;"><strong>Testing Tools:</strong></p>
                    <p>• Use Postman for comprehensive testing</p>
                    <p>• Try <span class="code">test_rest_api.py</span> for automated tests</p>
                    <p>• Monitor logs: <span class="code">railway logs</span></p>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

class CheckFreshnessRequest(BaseModel):
    url: str
    freshness_days: int = 30

class CheckFreshnessResponse(BaseModel):
    success: bool
    url: str
    is_fresh: bool
    last_crawled: Optional[str] = None
    days_since_crawl: Optional[int] = None
    error: Optional[str] = None

@app.post("/check-freshness", response_model=CheckFreshnessResponse)
async def check_url_freshness_endpoint(
    request: CheckFreshnessRequest,
    api_key: str = Depends(get_api_key)
) -> CheckFreshnessResponse:
    """
    Check if a URL was crawled recently and is considered fresh.
    
    This endpoint helps determine if a URL needs re-crawling based on the freshness period.
    """
    try:
        if not app_context:
            raise HTTPException(status_code=500, detail="Server not properly initialized")
        
        url = request.url
        freshness_days = request.freshness_days
        supabase_client = app_context.supabase_client
        
        is_fresh, last_crawled = check_url_freshness(supabase_client, url, freshness_days)
        
        days_since_crawl = None
        if last_crawled:
            days_since_crawl = (datetime.utcnow() - last_crawled).days
        
        return CheckFreshnessResponse(
            success=True,
            url=url,
            is_fresh=is_fresh,
            last_crawled=last_crawled.isoformat() if last_crawled else None,
            days_since_crawl=days_since_crawl
        )
        
    except Exception as e:
        return CheckFreshnessResponse(
            success=False,
            url=request.url,
            is_fresh=False,
            error=str(e)
        )

@app.post("/crawl/single", response_model=CrawlSinglePageResponse)
async def crawl_single_page(
    request: CrawlSinglePageRequest, 
    api_key: str = Depends(get_api_key)
) -> CrawlSinglePageResponse:
    """
    Crawl a single webpage and store the content with embeddings.
    
    This endpoint crawls a single URL, extracts the content, and stores it in the database
    with generated embeddings for future similarity searches.
    """
    try:
        if not app_context:
            raise HTTPException(status_code=500, detail="Server not properly initialized")
        
        url = request.url
        force_recrawl = request.force_recrawl
        crawler = app_context.crawler
        supabase_client = app_context.supabase_client
        
        # Check URL freshness unless force_recrawl is True
        if not force_recrawl:
            is_fresh, last_crawled = check_url_freshness(supabase_client, url)
            if is_fresh:
                return CrawlSinglePageResponse(
                    success=True,
                    url=url,
                    was_fresh=True,
                    last_crawled=last_crawled.isoformat() if last_crawled else None,
                    chunks_stored=0,
                    content_length=0
                )
        
        # Configure the crawl
        run_config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS, stream=False)
        
        # Perform the crawl
        result = await crawler.arun(url=url, config=run_config)
        
        if not result.success:
            return CrawlSinglePageResponse(
                success=False,
                error=f"Failed to crawl {url}: {result.error_message}"
            )
        
        if not result.markdown:
            return CrawlSinglePageResponse(
                success=False,
                error=f"No content extracted from {url}"
            )
        
        # Chunk the content
        chunks = smart_chunk_markdown(result.markdown)
        
        # Prepare data for storage
        urls = [url] * len(chunks)
        chunk_numbers = list(range(1, len(chunks) + 1))
        metadatas = []
        
        for i, chunk in enumerate(chunks):
            section_info = extract_section_info(chunk)
            metadata = {
                "source": urlparse(url).netloc,
                "title": result.metadata.get("title", ""),
                "headers": section_info["headers"],
                "word_count": section_info["word_count"],
                "char_count": section_info["char_count"],
                "chunk_number": i + 1,
                "total_chunks": len(chunks)
            }
            metadatas.append(metadata)
        
        # Create URL to full document mapping
        url_to_full_document = {url: result.markdown}
        
        # Store in database
        add_documents_to_supabase(
            client=supabase_client,
            urls=urls,
            chunk_numbers=chunk_numbers,
            contents=chunks,
            metadatas=metadatas,
            url_to_full_document=url_to_full_document
        )
        
        return CrawlSinglePageResponse(
            success=True,
            url=url,
            content_length=len(result.markdown),
            chunks_stored=len(chunks),
            was_fresh=False,
            last_crawled=None
        )
        
    except Exception as e:
        return CrawlSinglePageResponse(
            success=False,
            error=str(e)
        )

@app.post("/crawl/smart", response_model=SmartCrawlResponse)
async def smart_crawl_url(
    request: SmartCrawlRequest,
    api_key: str = Depends(get_api_key)
) -> SmartCrawlResponse:
    """
    Intelligently crawl a URL based on its type (sitemap, txt file, or regular webpage).
    
    This endpoint automatically detects the type of URL and applies the appropriate crawling strategy:
    - Sitemap XML: Extracts and crawls all URLs in the sitemap
    - Text file: Downloads and processes the text content
    - Regular webpage: Crawls the page and discovers internal links for recursive crawling
    """
    try:
        if not app_context:
            raise HTTPException(status_code=500, detail="Server not properly initialized")
        
        url = request.url
        max_depth = request.max_depth
        max_concurrent = request.max_concurrent
        chunk_size = request.chunk_size
        force_recrawl = request.force_recrawl
        
        crawler = app_context.crawler
        supabase_client = app_context.supabase_client
        
        crawl_type = "webpage"
        all_results = []
        skipped_fresh_count = 0
        
        if is_sitemap(url):
            crawl_type = "sitemap"
            sitemap_urls = parse_sitemap(url)
            if sitemap_urls:
                # Filter out fresh URLs unless force_recrawl is True
                urls_to_crawl = sitemap_urls[:50]  # Limit to 50 URLs
                if not force_recrawl:
                    stale_urls = get_stale_urls(supabase_client, urls_to_crawl)
                    skipped_fresh_count = len(urls_to_crawl) - len(stale_urls)
                    urls_to_crawl = stale_urls
                
                if urls_to_crawl:
                    all_results = await crawl_batch(crawler, urls_to_crawl, max_concurrent)
        elif is_txt(url):
            crawl_type = "txt_file"
            # Check freshness for single URL unless force_recrawl
            if not force_recrawl:
                is_fresh, _ = check_url_freshness(supabase_client, url)
                if is_fresh:
                    skipped_fresh_count = 1
                else:
                    all_results = await crawl_markdown_file(crawler, url)
            else:
                all_results = await crawl_markdown_file(crawler, url)
        else:
            crawl_type = "webpage"
            # For webpage crawling, check freshness of start URL
            start_urls = [url]
            if not force_recrawl:
                stale_urls = get_stale_urls(supabase_client, start_urls)
                skipped_fresh_count = len(start_urls) - len(stale_urls)
                if stale_urls:
                    all_results = await crawl_recursive_internal_links(crawler, stale_urls, max_depth, max_concurrent)
            else:
                all_results = await crawl_recursive_internal_links(crawler, start_urls, max_depth, max_concurrent)
        
        # Process and store all results
        total_chunks = 0
        for page_result in all_results:
            if page_result.get('markdown'):
                chunks = smart_chunk_markdown(page_result['markdown'], chunk_size)
                
                # Prepare data for storage
                page_url = page_result['url']
                urls = [page_url] * len(chunks)
                chunk_numbers = list(range(1, len(chunks) + 1))
                metadatas = []
                
                for i, chunk in enumerate(chunks):
                    section_info = extract_section_info(chunk)
                    metadata = {
                        "source": urlparse(page_url).netloc,
                        "title": page_result.get("title", ""),
                        "headers": section_info["headers"],
                        "word_count": section_info["word_count"],
                        "char_count": section_info["char_count"],
                        "chunk_number": i + 1,
                        "total_chunks": len(chunks)
                    }
                    metadatas.append(metadata)
                
                # Create URL to full document mapping
                url_to_full_document = {page_url: page_result['markdown']}
                
                # Store in database
                add_documents_to_supabase(
                    client=supabase_client,
                    urls=urls,
                    chunk_numbers=chunk_numbers,
                    contents=chunks,
                    metadatas=metadatas,
                    url_to_full_document=url_to_full_document
                )
                
                total_chunks += len(chunks)
        
        return SmartCrawlResponse(
            success=True,
            url=url,
            crawl_type=crawl_type,
            pages_crawled=len(all_results),
            chunks_stored=total_chunks,
            skipped_fresh_urls=skipped_fresh_count
        )
        
    except Exception as e:
        return SmartCrawlResponse(
            success=False,
            error=str(e)
        )

@app.get("/sources", response_model=AvailableSourcesResponse)
async def get_available_sources(api_key: str = Depends(get_api_key)) -> AvailableSourcesResponse:
    """
    Get all available sources based on unique source metadata values.
    
    This endpoint returns a list of all unique sources (domains) that have been crawled and stored
    in the database. This is useful for discovering what content is available for querying.
    """
    try:
        if not app_context:
            raise HTTPException(status_code=500, detail="Server not properly initialized")
        
        supabase_client = app_context.supabase_client
        
        # Use a direct query with the Supabase client
        result = supabase_client.from_('crawled_pages')\
            .select('metadata')\
            .not_.is_('metadata->>source', 'null')\
            .execute()
            
        # Use a set to efficiently track unique sources
        unique_sources = set()
        
        # Extract the source values from the result using a set for uniqueness
        if result.data:
            for item in result.data:
                source = item.get('metadata', {}).get('source')
                if source:
                    unique_sources.add(source)
        
        # Convert set to sorted list for consistent output
        sources = sorted(list(unique_sources))
        
        return AvailableSourcesResponse(
            success=True,
            sources=sources,
            count=len(sources)
        )
        
    except Exception as e:
        return AvailableSourcesResponse(
            success=False,
            error=str(e)
        )

@app.post("/query/rag")
async def perform_rag_query(
    request: RAGQueryRequest,
    api_key: str = Depends(get_api_key)
):
    """
    Perform a RAG (Retrieval Augmented Generation) query on the stored content.
    
    This endpoint searches the vector database for content relevant to the query and returns
    the matching documents. Optionally filter by source domain.
    """
    try:
        if not app_context:
            raise HTTPException(status_code=500, detail="Server not properly initialized")
        
        query = request.query
        source = request.source
        match_count = request.match_count
        
        supabase_client = app_context.supabase_client
        
        # Prepare filter if source is provided and not empty
        filter_metadata = None
        if source and source.strip():
            filter_metadata = {"source": source}
        
        # Perform the search
        results = search_documents(
            client=supabase_client,
            query=query,
            match_count=match_count,
            filter_metadata=filter_metadata
        )
        
        # Format the results
        formatted_results = []
        for result in results:
            formatted_results.append({
                "url": result.get("url"),
                "content": result.get("content"),
                "metadata": result.get("metadata"),
                "similarity": result.get("similarity")
            })
        
        return {
            "success": True,
            "query": query,
            "source_filter": source,
            "results": formatted_results,
            "count": len(formatted_results)
        }
        
    except Exception as e:
        return {
            "success": False,
            "query": query,
            "source_filter": None,
            "results": [],
            "count": 0,
            "error": str(e)
        }

# Helper functions for crawling (unchanged from original)
async def crawl_markdown_file(crawler: AsyncWebCrawler, url: str) -> List[Dict[str, Any]]:
    """Crawl a markdown file directly."""
    run_config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS, stream=False)
    result = await crawler.arun(url=url, config=run_config)
    
    if result.success and result.markdown:
        return [{'url': url, 'markdown': result.markdown}]
    return []

async def crawl_batch(crawler: AsyncWebCrawler, urls: List[str], max_concurrent: int = 10) -> List[Dict[str, Any]]:
    """Crawl multiple URLs concurrently."""
    run_config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS, stream=False)
    dispatcher = MemoryAdaptiveDispatcher(
        memory_threshold_percent=70.0,
        check_interval=1.0,
        max_session_permit=max_concurrent
    )
    
    results = await crawler.arun_many(urls=urls, config=run_config, dispatcher=dispatcher)
    return [{'url': result.url, 'markdown': result.markdown} for result in results if result.success and result.markdown]

async def crawl_recursive_internal_links(crawler: AsyncWebCrawler, start_urls: List[str], max_depth: int = 3, max_concurrent: int = 10) -> List[Dict[str, Any]]:
    """Recursively crawl internal links from start URLs up to a maximum depth."""
    run_config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS, stream=False)
    dispatcher = MemoryAdaptiveDispatcher(
        memory_threshold_percent=70.0,
        check_interval=1.0,
        max_session_permit=max_concurrent
    )

    visited = set()

    def normalize_url(url):
        return urldefrag(url)[0]

    current_urls = set([normalize_url(u) for u in start_urls])
    results_all = []

    for depth in range(max_depth):
        urls_to_crawl = [normalize_url(url) for url in current_urls if normalize_url(url) not in visited]
        if not urls_to_crawl:
            break

        results = await crawler.arun_many(urls=urls_to_crawl, config=run_config, dispatcher=dispatcher)
        next_level_urls = set()

        for result in results:
            norm_url = normalize_url(result.url)
            visited.add(norm_url)

            if result.success and result.markdown:
                results_all.append({'url': result.url, 'markdown': result.markdown})
                for link in result.links.get("internal", []):
                    next_url = normalize_url(link["href"])
                    if next_url not in visited:
                        next_level_urls.add(next_url)

        current_urls = next_level_urls

    return results_all

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "0.0.0.0")
    
    print(f"Starting Crawl4AI REST API server on {host}:{port}")
    uvicorn.run(app, host=host, port=port) 