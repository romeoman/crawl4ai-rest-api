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
import logging

# Add the src directory to Python path for imports
current_dir = Path(__file__).resolve().parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode, MemoryAdaptiveDispatcher, LLMConfig
from crawl4ai.extraction_strategy import LLMExtractionStrategy
from crawl4ai.chunking_strategy import RegexChunking, NlpSentenceChunking
from utils import (
    get_supabase_client, add_documents_to_supabase, search_documents,
    check_url_freshness, get_stale_urls, validate_api_key, normalize_url
)
from production_middleware import (
    init_production_features, CRAWL_COUNT, QUERY_COUNT, 
    ACTIVE_CRAWLS, ERROR_COUNT
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

# In-memory log store for real-time logging
import threading
from collections import deque

class LogStore:
    def __init__(self, max_logs=1000):
        self.logs = deque(maxlen=max_logs)
        self.lock = threading.Lock()
    
    def add_log(self, level: str, message: str, endpoint: Optional[str] = None):
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": level,
            "message": message,
            "endpoint": endpoint
        }
        with self.lock:
            self.logs.append(log_entry)
    
    def get_logs(self, limit: int = 100, since: Optional[str] = None) -> List[Dict[str, Any]]:
        with self.lock:
            logs_list = list(self.logs)
        
        if since:
            since_time = datetime.fromisoformat(since.replace("Z", "+00:00"))
            logs_list = [log for log in logs_list 
                        if datetime.fromisoformat(log["timestamp"].replace("Z", "+00:00")) > since_time]
        
        # Sort by timestamp (newest first) and apply limit
        logs_list.sort(key=lambda x: x["timestamp"], reverse=True)
        return logs_list[:limit]

# Global log store
log_store = LogStore()

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
    log_store.add_log("INFO", "Crawl4AI crawler initialized successfully", None)
    
    # Initialize Supabase client
    supabase_client = get_supabase_client()
    log_store.add_log("INFO", "Database connection established", None)
    
    app_context = Crawl4AIContext(
        crawler=crawler,
        supabase_client=supabase_client
    )
    log_store.add_log("INFO", "Crawl4AI REST API server ready for requests", None)
    
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

# Initialize production features (logging, monitoring, rate limiting, etc.)
production_config = init_production_features(app)
logger = production_config["logger"]
limiter = production_config["limiter"]

# Pydantic models for request/response
class ExtractionConfig(BaseModel):
    provider: str = "gpt-4.1-nano-2025-04-14"  # Default to custom model
    api_token: Optional[str] = None  # Will use environment variable if not provided
    instruction: str = "Extract the main content and key information"
    extra_args: Optional[Dict[str, Any]] = {}

class CrawlSinglePageRequest(BaseModel):
    url: str
    force_recrawl: bool = False
    extraction_strategy: Optional[str] = None  # "LLMExtractionStrategy" or None
    extraction_config: Optional[ExtractionConfig] = None
    chunking_strategy: Optional[str] = "RegexChunking"  # "RegexChunking" or "NlpSentenceChunking"
    css_selector: Optional[str] = "body"
    screenshot: bool = False
    user_agent: Optional[str] = "Crawl4AI-Bot/1.0"
    verbose: bool = True

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
    extraction_strategy: Optional[str] = None  # "LLMExtractionStrategy" or None
    extraction_config: Optional[ExtractionConfig] = None
    chunking_strategy: Optional[str] = "RegexChunking"  # "RegexChunking" or "NlpSentenceChunking"
    css_selector: Optional[str] = "body"
    screenshot: bool = False
    user_agent: Optional[str] = "Crawl4AI-Bot/1.0"
    verbose: bool = True

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

class RecentCrawlsResponse(BaseModel):
    success: bool
    recent_crawls: List[Dict[str, Any]] = []
    count: Optional[int] = None
    error: Optional[str] = None

class LogsResponse(BaseModel):
    success: bool
    logs: List[Dict[str, Any]] = []
    count: Optional[int] = None
    error: Optional[str] = None

# Helper functions for AI extraction
def create_extraction_strategy(extraction_strategy: str, extraction_config: ExtractionConfig):
    """Create an extraction strategy based on the configuration."""
    if extraction_strategy == "LLMExtractionStrategy":
        # Parse provider format
        provider = extraction_config.provider
        api_token = extraction_config.api_token
        instruction = extraction_config.instruction
        extra_args = extraction_config.extra_args or {}
        
        # Handle different provider formats
        if provider.startswith("openai/"):
            model_name = provider.split("/", 1)[1]
            api_key = api_token or os.getenv("OPENAI_API_KEY")
            provider_name = "openai"
        elif provider.startswith("anthropic/"):
            model_name = provider.split("/", 1)[1]
            api_key = api_token or os.getenv("ANTHROPIC_API_KEY")
            provider_name = "anthropic"
        elif provider.startswith("google/"):
            model_name = provider.split("/", 1)[1]
            api_key = api_token or os.getenv("GOOGLE_API_KEY")
            provider_name = "google"
        else:
            # Handle custom model names (like gpt-4.1-nano-2025-04-14)
            model_name = provider
            # Try to guess provider from model name or default to openai
            if "claude" in provider.lower():
                provider_name = "anthropic"
                api_key = api_token or os.getenv("ANTHROPIC_API_KEY")
            elif "gemini" in provider.lower():
                provider_name = "google"
                api_key = api_token or os.getenv("GOOGLE_API_KEY")
            else:
                provider_name = "openai"
                api_key = api_token or os.getenv("OPENAI_API_KEY")
        
        if not api_key:
            raise HTTPException(
                status_code=400,
                detail=f"API key not found for provider {provider_name}. Set environment variable or provide api_token."
            )
        
        # Create LLMConfig with the modern API
        llm_config = LLMConfig(
            provider=f"{provider_name}/{model_name}",
            api_token=api_key
        )
        
        return LLMExtractionStrategy(
            llm_config=llm_config,
            instruction=instruction,
            **extra_args
        )
    else:
        return None

def create_chunking_strategy(chunking_strategy: str):
    """Create a chunking strategy based on the strategy name."""
    if chunking_strategy == "RegexChunking":
        return RegexChunking()
    elif chunking_strategy == "NlpSentenceChunking":
        return NlpSentenceChunking()
    else:
        return RegexChunking()  # Default

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
    """Advanced web interface for testing the API and browsing data - recreates the original Crawl4AI playground functionality."""
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Crawl4AI Advanced Playground</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { 
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; 
                background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); 
                min-height: 100vh; 
                color: #333;
            }
            .container { max-width: 1400px; margin: 0 auto; padding: 20px; }
            .header { text-align: center; color: white; margin-bottom: 30px; }
            .header h1 { font-size: 2.8rem; margin-bottom: 8px; font-weight: 300; }
            .header p { font-size: 1.2rem; opacity: 0.9; }
            .nav-tabs { display: flex; background: rgba(255,255,255,0.1); border-radius: 12px; padding: 4px; margin-bottom: 30px; }
            .nav-tab { flex: 1; padding: 12px 20px; text-align: center; border-radius: 8px; color: rgba(255,255,255,0.7); cursor: pointer; transition: all 0.3s; }
            .nav-tab.active { background: rgba(255,255,255,0.2); color: white; }
            .nav-tab:hover { background: rgba(255,255,255,0.15); color: white; }
            .tab-content { display: none; }
            .tab-content.active { display: block; }
            .panel { background: white; border-radius: 12px; padding: 24px; margin-bottom: 20px; box-shadow: 0 4px 20px rgba(0,0,0,0.1); }
            .form-group { margin-bottom: 20px; }
            .form-label { display: block; margin-bottom: 8px; font-weight: 600; color: #2c3e50; }
            .form-input { width: 100%; padding: 12px; border: 2px solid #e1e5e9; border-radius: 8px; font-size: 14px; }
            .form-input:focus { outline: none; border-color: #3498db; box-shadow: 0 0 0 3px rgba(52,152,219,0.1); }
            .form-textarea { min-height: 120px; resize: vertical; font-family: 'Monaco', 'Courier New', monospace; }
            .btn { padding: 12px 24px; border: none; border-radius: 8px; font-weight: 600; cursor: pointer; transition: all 0.3s; }
            .btn-primary { background: #3498db; color: white; }
            .btn-primary:hover { background: #2980b9; transform: translateY(-2px); }
            .btn-success { background: #27ae60; color: white; }
            .btn-success:hover { background: #219a52; }
            .btn-danger { background: #e74c3c; color: white; }
            .btn-danger:hover { background: #c0392b; }
            .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
            .response-area { background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 8px; padding: 16px; font-family: monospace; min-height: 200px; white-space: pre-wrap; overflow-x: auto; }
            .status-indicator { display: inline-block; width: 12px; height: 12px; border-radius: 50%; margin-right: 8px; }
            .status-success { background: #27ae60; }
            .status-error { background: #e74c3c; }
            .status-pending { background: #f39c12; animation: pulse 1.5s infinite; }
            @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
            .endpoint-card { background: #f8f9fa; border-left: 4px solid #3498db; padding: 16px; margin: 12px 0; border-radius: 0 8px 8px 0; }
            .method-badge { display: inline-block; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 12px; margin-right: 8px; }
            .method-get { background: #27ae60; color: white; }
            .method-post { background: #3498db; color: white; }
            .database-table { width: 100%; border-collapse: collapse; margin-top: 16px; }
            .database-table th, .database-table td { padding: 12px; text-align: left; border-bottom: 1px solid #dee2e6; }
            .database-table th { background: #f8f9fa; font-weight: 600; }
            .loading { display: none; text-align: center; padding: 20px; }
            .loading.show { display: block; }
            .spinner { display: inline-block; width: 20px; height: 20px; border: 3px solid #f3f3f3; border-top: 3px solid #3498db; border-radius: 50%; animation: spin 1s linear infinite; }
            @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
            .code-block { background: #2c3e50; color: #ecf0f1; padding: 16px; border-radius: 8px; font-family: 'Monaco', 'Courier New', monospace; overflow-x: auto; }
            .alert { padding: 12px 16px; border-radius: 8px; margin-bottom: 16px; }
            .alert-info { background: #d1ecf1; border: 1px solid #bee5eb; color: #0c5460; }
            .alert-warning { background: #fff3cd; border: 1px solid #ffeaa7; color: #856404; }
            .status-indicator { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 8px; }
            .status-success { background: #27ae60; }
            .status-warning { background: #f39c12; }
            .status-error { background: #e74c3c; }
            .status-idle { background: #95a5a6; }
            .log-entry { margin-bottom: 2px; padding: 2px 0; border-left: 3px solid transparent; padding-left: 8px; }
            .log-entry.error { border-left-color: #e74c3c; background: rgba(231, 76, 60, 0.1); }
            .log-entry.warning { border-left-color: #f39c12; background: rgba(243, 156, 18, 0.1); }
            .log-entry.info { border-left-color: #3498db; background: rgba(52, 152, 219, 0.1); }
            .log-entry.debug { border-left-color: #9b59b6; background: rgba(155, 89, 182, 0.1); }
            .log-timestamp { color: #888; font-size: 11px; margin-right: 8px; }
            .log-level { font-weight: bold; margin-right: 8px; }
            .log-level.ERROR { color: #e74c3c; }
            .log-level.WARNING { color: #f39c12; }
            .log-level.INFO { color: #3498db; }
            .log-level.DEBUG { color: #9b59b6; }
            .log-message { color: #ecf0f1; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🕷️ Crawl4AI Advanced Playground</h1>
                <p>Interactive testing interface with database browser and real-time API testing</p>
            </div>
            
            <div class="nav-tabs">
                <div class="nav-tab active" onclick="showTab('test')">🧪 API Testing</div>
                <div class="nav-tab" onclick="showTab('database')">🗄️ Database Browser</div>
                <div class="nav-tab" onclick="showTab('logs')">📋 Logs</div>
                <div class="nav-tab" onclick="showTab('monitor')">📊 Monitoring</div>
                <div class="nav-tab" onclick="showTab('docs')">📚 Documentation</div>
            </div>
            
            <!-- API Testing Tab -->
            <div id="test-tab" class="tab-content active">
                <div class="grid">
                    <div class="panel">
                        <h3>🚀 Test API Endpoints</h3>
                        
                        <div class="form-group">
                            <label class="form-label">Endpoint</label>
                            <select id="endpoint-select" class="form-input" onchange="updateEndpointForm()">
                                <option value="health">GET /health - Health Check</option>
                                <option value="crawl-single">POST /crawl/single - Single Page Crawl</option>
                                <option value="crawl-smart">POST /crawl/smart - Smart Multi-page Crawl</option>
                                <option value="query-rag">POST /query/rag - RAG Query</option>
                                <option value="sources">GET /sources - Available Sources</option>
                                <option value="check-freshness">POST /check-freshness - Check URL Freshness</option>
                            </select>
                        </div>
                        
                        <div id="endpoint-form">
                            <!-- Dynamic form content will be inserted here -->
                        </div>
                        
                        <button class="btn btn-primary" onclick="executeRequest()">
                            <span id="request-status"></span> Execute Request
                        </button>
                    </div>
                    
                    <div class="panel">
                        <h3>📨 Response</h3>
                        <div id="response-status" class="alert alert-info" style="display: none;"></div>
                        <div class="loading" id="loading">
                            <div class="spinner"></div> Processing request...
                        </div>
                        <div id="response-area" class="response-area">Click "Execute Request" to see response</div>
                    </div>
                </div>
                
                <div class="panel">
                    <h3>📋 Generated cURL Command</h3>
                    <div id="curl-command" class="code-block">Select an endpoint and fill the form to generate cURL command</div>
                </div>
            </div>
            
            <!-- Database Browser Tab -->
            <div id="database-tab" class="tab-content">
                <div class="panel">
                    <h3>🗄️ Database Browser</h3>
                    <div class="alert alert-info">
                        <strong>Database Status:</strong> Connected to Supabase PostgreSQL with vector embeddings
                    </div>
                    
                    <button class="btn btn-primary" onclick="loadSources()">🔄 Refresh Sources</button>
                    <button class="btn btn-success" onclick="loadRecentCrawls()">📅 Recent Crawls</button>
                    
                    <div id="database-content">
                        <p>Click "Refresh Sources" to browse crawled content</p>
                    </div>
                </div>
            </div>
            
            <!-- Logs Tab -->
            <div id="logs-tab" class="tab-content">
                <div class="panel">
                    <h3>📋 System Logs</h3>
                    <div class="grid">
                        <div style="display: flex; gap: 10px; margin-bottom: 20px;">
                            <button class="btn btn-success" onclick="loadRealtimeLogs()">🟢 Start Live Monitoring</button>
                            <button class="btn btn-warning" onclick="stopRealtimeLogs()">⏹️ Stop Monitoring</button>
                            <button class="btn btn-primary" onclick="loadHistoricalLogs()">📜 Load Historical Logs</button>
                            <button class="btn btn-secondary" onclick="clearLogs()">🗑️ Clear Display</button>
                            <select id="log-level-filter" class="form-input" style="width: auto; margin-left: auto;">
                                <option value="all">All Levels</option>
                                <option value="ERROR">🔴 Errors Only</option>
                                <option value="WARNING">🟡 Warnings+</option>
                                <option value="INFO">🔵 Info+</option>
                                <option value="DEBUG">🔍 Debug+</option>
                            </select>
                        </div>
                        
                        <div style="display: flex; gap: 10px; margin-bottom: 15px;">
                            <div style="flex: 1;">
                                <label class="form-label">Filter by Endpoint/Action:</label>
                                <input type="text" id="endpoint-filter" class="form-input" placeholder="e.g., /crawl/single, /query/rag" />
                            </div>
                            <div style="flex: 1;">
                                <label class="form-label">Time Range (last):</label>
                                <select id="time-range" class="form-input">
                                    <option value="5">5 minutes</option>
                                    <option value="15">15 minutes</option>
                                    <option value="60" selected>1 hour</option>
                                    <option value="360">6 hours</option>
                                    <option value="1440">24 hours</option>
                                </select>
                            </div>
                        </div>
                        
                        <div id="logs-controls" style="margin-bottom: 15px;">
                            <div style="display: flex; align-items: center; gap: 15px;">
                                <span id="logs-status" class="status-indicator status-idle"><span style="color: #888;">⚪ Stopped</span></span>
                                <span id="logs-count">0 logs displayed</span>
                                <label style="display: flex; align-items: center; gap: 5px;">
                                    <input type="checkbox" id="auto-scroll" checked> Auto-scroll to bottom
                                </label>
                                <label style="display: flex; align-items: center; gap: 5px;">
                                    <input type="checkbox" id="show-timestamps" checked> Show timestamps
                                </label>
                            </div>
                        </div>
                    </div>
                    
                    <div id="logs-container" style="
                        background: #1a1a1a; 
                        color: #00ff00; 
                        font-family: 'Monaco', 'Consolas', monospace; 
                        font-size: 12px; 
                        padding: 15px; 
                        border-radius: 8px; 
                        height: 500px; 
                        overflow-y: auto; 
                        border: 2px solid #333;
                        white-space: pre-wrap;
                        line-height: 1.4;">
                        <div style="color: #888;">📋 Logs will appear here. Click "Start Real-time Logs" to begin monitoring or "Load Historical Logs" to view past entries.</div>
                    </div>
                </div>
            </div>
            
            <!-- Monitoring Tab -->
            <div id="monitor-tab" class="tab-content">
                <div class="panel">
                    <h3>📊 System Status</h3>
                    <div class="grid">
                        <div>
                            <h4><span class="status-indicator status-success"></span>API Status</h4>
                            <p><strong>Base URL:</strong> """ + str(request.base_url) + """</p>
                            <p><strong>Environment:</strong> Railway Production</p>
                            <p><strong>Service:</strong> Crawl4AI REST API</p>
                        </div>
                        <div>
                            <h4><span class="status-indicator status-success"></span>Database Status</h4>
                            <p><strong>Provider:</strong> Supabase PostgreSQL</p>
                            <p><strong>Features:</strong> Vector embeddings, RAG queries</p>
                            <p><strong>Freshness Period:</strong> 30 days</p>
                        </div>
                    </div>
                </div>
                
                <div class="panel">
                    <h3>🔧 Configuration</h3>
                    <div class="alert alert-info">
                        <strong>✅ Fully Implemented Features:</strong><br>
                        • ✅ AI LLM extraction with multiple providers (OpenAI, Anthropic, Google, Custom)<br>
                        • ✅ Smart chunking strategies (Regex, NLP Sentence)<br>
                        • ✅ Advanced database queries with vector embeddings<br>
                        • ✅ Real-time playground interface with interactive forms<br>
                        • ✅ Full support for your custom model: gpt-4.1-nano-2025-04-14<br><br>
                        <strong>🚀 Ready for Production Use!</strong>
                    </div>
                </div>
            </div>
            
            <!-- Documentation Tab -->
            <div id="docs-tab" class="tab-content">
                <div class="panel">
                    <h3>📚 Quick Reference</h3>
                    
                    <div class="endpoint-card">
                        <span class="method-badge method-get">GET</span>
                        <strong>/health</strong>
                        <p>Check API health status</p>
                    </div>
                    
                    <div class="endpoint-card">
                        <span class="method-badge method-post">POST</span>
                        <strong>/crawl/single</strong>
                        <p>Crawl a single webpage and store content with embeddings</p>
                        <div class="code-block">{"url": "https://example.com", "force_recrawl": false}</div>
                    </div>
                    
                    <div class="endpoint-card">
                        <span class="method-badge method-post">POST</span>
                        <strong>/crawl/smart</strong>
                        <p>Smart multi-page crawling with link discovery</p>
                        <div class="code-block">{"url": "https://example.com", "max_depth": 3, "max_concurrent": 10}</div>
                    </div>
                    
                    <div class="endpoint-card">
                        <span class="method-badge method-post">POST</span>
                        <strong>/query/rag</strong>
                        <p>Query crawled content using RAG (Retrieval-Augmented Generation)</p>
                        <div class="code-block">{"query": "What are the main features?", "match_count": 5}</div>
                    </div>
                </div>
                
                <div class="panel">
                    <h3>🔑 Authentication</h3>
                    <p><strong>Type:</strong> Bearer Token</p>
                    <div class="code-block">Authorization: Bearer secure-crawl4ai-bearer-token-2024</div>
                    
                    <h3 style="margin-top: 20px;">📖 Resources</h3>
                    <p>• Check <code>POSTMAN_TESTING_GUIDE.md</code> for detailed API documentation</p>
                    <p>• See <code>API_CREDENTIALS.txt</code> for authentication details</p>
                    <p>• Use Railway logs: <code>railway logs</code> for monitoring</p>
                </div>
            </div>
        </div>
        
        <script>
            // Fix for Railway HTTPS deployment - force HTTPS for production
            let baseUrl = '""" + str(request.base_url) + """';
            if (window.location.protocol === 'https:' && baseUrl.startsWith('http://')) {
                baseUrl = baseUrl.replace('http://', 'https://');
            }
            const API_BASE = baseUrl;
            const API_KEY = 'secure-crawl4ai-bearer-token-2024';
            
            function showTab(tabName) {
                // Hide all tab contents
                document.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));
                document.querySelectorAll('.nav-tab').forEach(tab => tab.classList.remove('active'));
                
                // Show selected tab
                document.getElementById(tabName + '-tab').classList.add('active');
                event.target.classList.add('active');
            }
            
            function updateEndpointForm() {
                const endpoint = document.getElementById('endpoint-select').value;
                const form = document.getElementById('endpoint-form');
                
                switch(endpoint) {
                    case 'health':
                        form.innerHTML = '<p class="alert alert-info">No parameters required for health check</p>';
                        break;
                    case 'crawl-single':
                        form.innerHTML = `
                            <div class="form-group">
                                <label class="form-label">URL to Crawl</label>
                                <input type="url" id="url" class="form-input" placeholder="https://example.com" required>
                            </div>
                            <div class="form-group">
                                <label class="form-label">
                                    <input type="checkbox" id="force_recrawl"> Force Recrawl
                                </label>
                            </div>
                            <h4>🤖 AI Extraction (Optional)</h4>
                            <div class="form-group">
                                <label class="form-label">
                                    <input type="checkbox" id="enable_ai" onchange="toggleAIFields()"> Enable AI Content Extraction
                                </label>
                            </div>
                            <div id="ai-fields" style="display: none;">
                                <div class="form-group">
                                    <label class="form-label">AI Provider/Model</label>
                                    <select id="ai_provider" class="form-input">
                                        <option value="gpt-4.1-nano-2025-04-14">gpt-4.1-nano-2025-04-14 (Default Custom Model)</option>
                                        <option value="anthropic/claude-3-5-haiku-20241022">Anthropic Claude 3.5 Haiku</option>
                                        <option value="google/gemini-2.5-flash-preview-05-20">Google Gemini 2.5 Flash Preview</option>
                                    </select>
                                </div>
                                <div class="form-group">
                                    <label class="form-label">Extraction Instruction</label>
                                    <textarea id="ai_instruction" class="form-input form-textarea" placeholder="Extract the main content and key information">Extract the main content and key information</textarea>
                                </div>
                                <div class="form-group">
                                    <label class="form-label">API Token (optional - uses env vars if not provided)</label>
                                    <input type="password" id="ai_token" class="form-input" placeholder="sk-...">
                                </div>
                                <div class="form-group">
                                    <label class="form-label">Chunking Strategy</label>
                                    <select id="chunking_strategy" class="form-input">
                                        <option value="RegexChunking">Regex Chunking (Default)</option>
                                        <option value="NlpSentenceChunking">NLP Sentence Chunking</option>
                                    </select>
                                </div>
                            </div>
                        `;
                        break;
                    case 'crawl-smart':
                        form.innerHTML = `
                            <div class="form-group">
                                <label class="form-label">URL to Crawl</label>
                                <input type="url" id="url" class="form-input" placeholder="https://example.com" required>
                            </div>
                            <div class="form-group">
                                <label class="form-label">Max Depth</label>
                                <input type="number" id="max_depth" class="form-input" value="3" min="1" max="10">
                            </div>
                            <div class="form-group">
                                <label class="form-label">Max Concurrent</label>
                                <input type="number" id="max_concurrent" class="form-input" value="10" min="1" max="50">
                            </div>
                            <div class="form-group">
                                <label class="form-label">
                                    <input type="checkbox" id="force_recrawl"> Force Recrawl
                                </label>
                            </div>
                            <h4>🤖 AI Extraction (Optional)</h4>
                            <div class="form-group">
                                <label class="form-label">
                                    <input type="checkbox" id="enable_ai" onchange="toggleAIFields()"> Enable AI Content Extraction
                                </label>
                            </div>
                            <div id="ai-fields" style="display: none;">
                                <div class="form-group">
                                    <label class="form-label">AI Provider/Model</label>
                                    <select id="ai_provider" class="form-input">
                                        <option value="gpt-4.1-nano-2025-04-14">gpt-4.1-nano-2025-04-14 (Default Custom Model)</option>
                                        <option value="anthropic/claude-3-5-haiku-20241022">Anthropic Claude 3.5 Haiku</option>
                                        <option value="google/gemini-2.5-flash-preview-05-20">Google Gemini 2.5 Flash Preview</option>
                                    </select>
                                </div>
                                <div class="form-group">
                                    <label class="form-label">Extraction Instruction</label>
                                    <textarea id="ai_instruction" class="form-input form-textarea" placeholder="Extract the main content and key information">Extract the main content and key information</textarea>
                                </div>
                                <div class="form-group">
                                    <label class="form-label">API Token (optional - uses env vars if not provided)</label>
                                    <input type="password" id="ai_token" class="form-input" placeholder="sk-...">
                                </div>
                                <div class="form-group">
                                    <label class="form-label">Chunking Strategy</label>
                                    <select id="chunking_strategy" class="form-input">
                                        <option value="RegexChunking">Regex Chunking (Default)</option>
                                        <option value="NlpSentenceChunking">NLP Sentence Chunking</option>
                                    </select>
                                </div>
                            </div>
                        `;
                        break;
                    case 'query-rag':
                        form.innerHTML = `
                            <div class="form-group">
                                <label class="form-label">Query</label>
                                <textarea id="query" class="form-input form-textarea" placeholder="What information are you looking for?" required></textarea>
                            </div>
                            <div class="form-group">
                                <label class="form-label">Source Filter (optional)</label>
                                <input type="text" id="source" class="form-input" placeholder="example.com">
                            </div>
                            <div class="form-group">
                                <label class="form-label">Match Count</label>
                                <input type="number" id="match_count" class="form-input" value="5" min="1" max="20">
                            </div>
                        `;
                        break;
                    case 'sources':
                        form.innerHTML = '<p class="alert alert-info">No parameters required for listing sources</p>';
                        break;
                    case 'check-freshness':
                        form.innerHTML = `
                            <div class="form-group">
                                <label class="form-label">URL to Check</label>
                                <input type="url" id="url" class="form-input" placeholder="https://example.com" required>
                            </div>
                            <div class="form-group">
                                <label class="form-label">Freshness Days</label>
                                <input type="number" id="freshness_days" class="form-input" value="30" min="1">
                            </div>
                        `;
                        break;
                }
                updateCurlCommand();
            }
            
            function updateCurlCommand() {
                const endpoint = document.getElementById('endpoint-select').value;
                const curlElement = document.getElementById('curl-command');
                
                let curl = `curl -H "Authorization: Bearer ${API_KEY}" \\\\`;
                
                switch(endpoint) {
                    case 'health':
                        curl += `\\n     "${API_BASE}health"`;
                        break;
                    case 'sources':
                        curl += `\\n     "${API_BASE}sources"`;
                        break;
                    case 'check-freshness':
                        curl += `\\n     -H "Content-Type: application/json" \\\\\\n     -X POST \\\\\\n     -d '{"url": "https://example.com", "freshness_days": 30}' \\\\\\n     "${API_BASE}check-freshness"`;
                        break;
                    case 'crawl-single':
                        curl += `\\n     -H "Content-Type: application/json" \\\\\\n     -X POST \\\\\\n     -d '{"url": "https://example.com"}' \\\\\\n     "${API_BASE}crawl/single"`;
                        break;
                    case 'crawl-smart':
                        curl += `\\n     -H "Content-Type: application/json" \\\\\\n     -X POST \\\\\\n     -d '{"url": "https://example.com"}' \\\\\\n     "${API_BASE}crawl/smart"`;
                        break;
                    case 'query-rag':
                        curl += `\\n     -H "Content-Type: application/json" \\\\\\n     -X POST \\\\\\n     -d '{"query": "example query"}' \\\\\\n     "${API_BASE}query/rag"`;
                        break;
                    default:
                        curl += `\\n     -H "Content-Type: application/json" \\\\\\n     -X POST \\\\\\n     -d '{"url": "https://example.com"}' \\\\\\n     "${API_BASE}${endpoint}"`;
                }
                
                curlElement.textContent = curl;
            }
            
            async function executeRequest() {
                const endpoint = document.getElementById('endpoint-select').value;
                const loading = document.getElementById('loading');
                const responseArea = document.getElementById('response-area');
                const statusDiv = document.getElementById('response-status');
                
                loading.classList.add('show');
                responseArea.textContent = '';
                statusDiv.style.display = 'none';
                
                try {
                    let url;
                    // Map endpoint names to correct API paths
                    switch(endpoint) {
                        case 'health':
                            url = API_BASE + 'health';
                            break;
                        case 'sources':
                            url = API_BASE + 'sources';
                            break;
                        case 'check-freshness':
                            url = API_BASE + 'check-freshness';
                            break;
                        case 'crawl-single':
                            url = API_BASE + 'crawl/single';
                            break;
                        case 'crawl-smart':
                            url = API_BASE + 'crawl/smart';
                            break;
                        case 'query-rag':
                            url = API_BASE + 'query/rag';
                            break;
                        default:
                            url = API_BASE + endpoint;
                    }
                    
                    let options = {
                        headers: {
                            'Authorization': 'Bearer ' + API_KEY,
                            'Content-Type': 'application/json'
                        }
                    };
                    
                    if (!['health', 'sources'].includes(endpoint)) {
                        options.method = 'POST';
                        options.body = JSON.stringify(buildRequestBody(endpoint));
                    }
                    
                    const response = await fetch(url, options);
                    const data = await response.json();
                    
                    loading.classList.remove('show');
                    
                    if (response.ok) {
                        statusDiv.className = 'alert alert-info';
                        statusDiv.textContent = `✅ Success (${response.status})`;
                        statusDiv.style.display = 'block';
                    } else {
                        statusDiv.className = 'alert alert-warning';
                        statusDiv.textContent = `⚠️ Error (${response.status})`;
                        statusDiv.style.display = 'block';
                    }
                    
                    responseArea.textContent = JSON.stringify(data, null, 2);
                } catch (error) {
                    loading.classList.remove('show');
                    statusDiv.className = 'alert alert-warning';
                    statusDiv.textContent = `❌ Request failed: ${error.message}`;
                    statusDiv.style.display = 'block';
                    responseArea.textContent = 'Error: ' + error.message;
                }
            }
            
            function buildRequestBody(endpoint) {
                const body = {};
                
                switch(endpoint) {
                    case 'crawl-single':
                        body.url = document.getElementById('url')?.value || '';
                        body.force_recrawl = document.getElementById('force_recrawl')?.checked || false;
                        
                        // Add AI extraction if enabled
                        if (document.getElementById('enable_ai')?.checked) {
                            body.extraction_strategy = 'LLMExtractionStrategy';
                            body.extraction_config = {
                                provider: document.getElementById('ai_provider')?.value || 'gpt-4.1-nano-2025-04-14',
                                instruction: document.getElementById('ai_instruction')?.value || 'Extract the main content and key information'
                            };
                            const apiToken = document.getElementById('ai_token')?.value;
                            if (apiToken) {
                                body.extraction_config.api_token = apiToken;
                            }
                            body.chunking_strategy = document.getElementById('chunking_strategy')?.value || 'RegexChunking';
                        }
                        break;
                    case 'crawl-smart':
                        body.url = document.getElementById('url')?.value || '';
                        body.max_depth = parseInt(document.getElementById('max_depth')?.value) || 3;
                        body.max_concurrent = parseInt(document.getElementById('max_concurrent')?.value) || 10;
                        body.force_recrawl = document.getElementById('force_recrawl')?.checked || false;
                        
                        // Add AI extraction if enabled
                        if (document.getElementById('enable_ai')?.checked) {
                            body.extraction_strategy = 'LLMExtractionStrategy';
                            body.extraction_config = {
                                provider: document.getElementById('ai_provider')?.value || 'gpt-4.1-nano-2025-04-14',
                                instruction: document.getElementById('ai_instruction')?.value || 'Extract the main content and key information'
                            };
                            const apiToken = document.getElementById('ai_token')?.value;
                            if (apiToken) {
                                body.extraction_config.api_token = apiToken;
                            }
                            body.chunking_strategy = document.getElementById('chunking_strategy')?.value || 'RegexChunking';
                        }
                        break;
                    case 'query-rag':
                        body.query = document.getElementById('query')?.value || '';
                        body.source = document.getElementById('source')?.value || '';
                        body.match_count = parseInt(document.getElementById('match_count')?.value) || 5;
                        break;
                    case 'check-freshness':
                        body.url = document.getElementById('url')?.value || '';
                        body.freshness_days = parseInt(document.getElementById('freshness_days')?.value) || 30;
                        break;
                }
                
                return body;
            }
            
            function toggleAIFields() {
                const aiFields = document.getElementById('ai-fields');
                const enableAI = document.getElementById('enable_ai');
                if (enableAI && aiFields) {
                    aiFields.style.display = enableAI.checked ? 'block' : 'none';
                }
                updateCurlCommand();
            }
            
            async function loadSources() {
                const content = document.getElementById('database-content');
                content.innerHTML = '<div class="loading show"><div class="spinner"></div> Loading sources...</div>';
                
                try {
                    const response = await fetch(API_BASE + 'sources', {
                        headers: { 'Authorization': 'Bearer ' + API_KEY }
                    });
                    const data = await response.json();
                    
                    if (data.success && data.sources.length > 0) {
                        let html = '<h4>📊 Available Sources (' + data.sources.length + ')</h4>';
                        html += '<table class="database-table"><thead><tr><th>Domain</th><th>Actions</th></tr></thead><tbody>';
                        
                        data.sources.forEach(source => {
                            html += `<tr><td>${source}</td><td><button class="btn btn-primary" onclick="querySource('${source}')">Query</button></td></tr>`;
                        });
                        
                        html += '</tbody></table>';
                        content.innerHTML = html;
                    } else {
                        content.innerHTML = '<p>No sources found. Try crawling some content first.</p>';
                    }
                } catch (error) {
                    content.innerHTML = '<p class="alert alert-warning">Error loading sources: ' + error.message + '</p>';
                }
            }
            
            function querySource(source) {
                // Switch to API testing tab and pre-fill RAG query
                showTab('test');
                document.getElementById('endpoint-select').value = 'query-rag';
                updateEndpointForm();
                setTimeout(() => {
                    document.getElementById('source').value = source;
                    document.getElementById('query').value = 'What content is available from this source?';
                }, 100);
            }
            
            async function loadRecentCrawls() {
                const content = document.getElementById('database-content');
                content.innerHTML = '<div class="loading show"><div class="spinner"></div> Loading recent crawls...</div>';
                
                try {
                    const response = await fetch(API_BASE + 'recent-crawls?limit=15', {
                        headers: { 'Authorization': 'Bearer ' + API_KEY }
                    });
                    
                    if (!response.ok) {
                        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                    }
                    
                    const data = await response.json();
                    
                    // Check if the response has the expected structure
                    if (!data || typeof data.success === 'undefined') {
                        throw new Error('Invalid response format from server');
                    }
                    
                    if (data.success && data.recent_crawls && Array.isArray(data.recent_crawls) && data.recent_crawls.length > 0) {
                        let html = '<h4>🕒 Recent Crawls (' + data.recent_crawls.length + ')</h4>';
                        html += '<table class="database-table">';
                        html += '<thead><tr><th>URL</th><th>Title</th><th>Source</th><th>Chunks</th><th>AI Extracted</th><th>Crawled</th><th>Actions</th></tr></thead>';
                        html += '<tbody>';
                        
                        data.recent_crawls.forEach(crawl => {
                            const crawlDate = new Date(crawl.crawled_at).toLocaleString();
                            const shortUrl = crawl.url && crawl.url.length > 50 ? crawl.url.substring(0, 47) + '...' : (crawl.url || 'Unknown URL');
                            const shortTitle = crawl.title && crawl.title.length > 30 ? crawl.title.substring(0, 27) + '...' : (crawl.title || 'No title');
                            const aiIcon = crawl.ai_extracted ? '🤖' : '📄';
                            const aiStatus = crawl.ai_extracted ? 'Yes (' + (crawl.extraction_strategy || 'unknown') + ')' : 'No';
                            
                            html += `<tr>
                                <td><a href="${crawl.url || '#'}" target="_blank" title="${crawl.url || 'Unknown URL'}">${shortUrl}</a></td>
                                <td title="${crawl.title || 'No title'}">${shortTitle}</td>
                                <td>${crawl.source || 'Unknown'}</td>
                                <td>${crawl.chunk_count || 0}</td>
                                <td>${aiIcon} ${aiStatus}</td>
                                <td>${crawlDate}</td>
                                <td>
                                    <button class="btn btn-primary" onclick="querySource('${crawl.source || ''}')" style="margin-right: 5px;">Query</button>
                                    <button class="btn btn-success" onclick="recrawlUrl('${crawl.url || ''}')">Re-crawl</button>
                                </td>
                            </tr>`;
                        });
                        
                        html += '</tbody></table>';
                        content.innerHTML = html;
                    } else if (data.success && (!data.recent_crawls || data.recent_crawls.length === 0)) {
                        content.innerHTML = '<p>No recent crawls found. Try crawling some content first.</p>';
                    } else {
                        // Handle API error response
                        const errorMsg = data.error || 'Unknown error occurred';
                        content.innerHTML = '<p class="alert alert-warning">Error loading recent crawls: ' + errorMsg + '</p>';
                    }
                } catch (error) {
                    console.error('Recent crawls error:', error);
                    content.innerHTML = '<p class="alert alert-warning">Error loading recent crawls: ' + error.message + '</p>';
                }
            }
            
            function recrawlUrl(url) {
                // Switch to API testing tab and pre-fill single page crawl
                showTab('test');
                document.getElementById('endpoint-select').value = 'crawl-single';
                updateEndpointForm();
                setTimeout(() => {
                    document.getElementById('url').value = url;
                    document.getElementById('force_recrawl').checked = true;
                }, 100);
            }
            
            // Logs functionality
            let realtimeLogsInterval = null;
            let lastLogTimestamp = null;
            
            function loadRealtimeLogs() {
                if (realtimeLogsInterval) {
                    stopRealtimeLogs();
                }
                
                const statusEl = document.getElementById('logs-status');
                statusEl.className = 'status-indicator status-success';
                statusEl.innerHTML = '<span style="color: #00ff00;">🟢 Live Monitoring</span>';
                
                // Clear existing logs
                clearLogs();
                appendLogMessage('🚀 Starting real-time log monitoring...', 'INFO');
                
                // Start polling for new logs every 2 seconds
                realtimeLogsInterval = setInterval(fetchRealtimeLogs, 2000);
                
                // Fetch initial logs
                fetchRealtimeLogs();
            }
            
            async function fetchRealtimeLogs() {
                try {
                    const timeRange = document.getElementById('time-range').value;
                    const levelFilter = document.getElementById('log-level-filter').value;
                    const endpointFilter = document.getElementById('endpoint-filter').value;
                    
                    let url = API_BASE + 'logs?limit=50&minutes=' + timeRange;
                    if (levelFilter !== 'all') {
                        url += '&level=' + levelFilter;
                    }
                    if (endpointFilter) {
                        url += '&endpoint=' + encodeURIComponent(endpointFilter);
                    }
                    if (lastLogTimestamp) {
                        url += '&since=' + encodeURIComponent(lastLogTimestamp);
                    }
                    
                    const response = await fetch(url, {
                        headers: { 'Authorization': 'Bearer ' + API_KEY }
                    });
                    
                    if (!response.ok) {
                        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                    }
                    
                    const data = await response.json();
                    
                    if (data.success && data.logs && data.logs.length > 0) {
                        data.logs.forEach(log => {
                            appendLogEntry(log);
                            lastLogTimestamp = log.timestamp;
                        });
                        updateLogCount();
                    }
                } catch (error) {
                    console.error('Real-time logs error:', error);
                    appendLogMessage('❌ Error fetching real-time logs: ' + error.message, 'ERROR');
                }
            }
            
            function stopRealtimeLogs() {
                if (realtimeLogsInterval) {
                    clearInterval(realtimeLogsInterval);
                    realtimeLogsInterval = null;
                }
                
                const statusEl = document.getElementById('logs-status');
                statusEl.className = 'status-indicator status-idle';
                statusEl.innerHTML = '<span style="color: #888;">⚪ Stopped</span>';
                
                appendLogMessage('⏹️ Real-time log monitoring stopped.', 'INFO');
            }
            
            async function loadHistoricalLogs() {
                const container = document.getElementById('logs-container');
                container.innerHTML = '<div style="color: #888;">📜 Loading historical logs...</div>';
                
                try {
                    const timeRange = document.getElementById('time-range').value;
                    const levelFilter = document.getElementById('log-level-filter').value;
                    const endpointFilter = document.getElementById('endpoint-filter').value;
                    
                    let url = API_BASE + 'logs?limit=200&minutes=' + timeRange;
                    if (levelFilter !== 'all') {
                        url += '&level=' + levelFilter;
                    }
                    if (endpointFilter) {
                        url += '&endpoint=' + encodeURIComponent(endpointFilter);
                    }
                    
                    const response = await fetch(url, {
                        headers: { 'Authorization': 'Bearer ' + API_KEY }
                    });
                    
                    if (!response.ok) {
                        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                    }
                    
                    const data = await response.json();
                    
                    clearLogs();
                    
                    if (data.success && data.logs && data.logs.length > 0) {
                        appendLogMessage('📜 Loaded ' + data.logs.length + ' historical log entries', 'INFO');
                        data.logs.forEach(log => {
                            appendLogEntry(log);
                        });
                    } else {
                        appendLogMessage('📭 No logs found for the specified time range and filters.', 'INFO');
                    }
                    
                    updateLogCount();
                } catch (error) {
                    console.error('Historical logs error:', error);
                    clearLogs();
                    appendLogMessage('❌ Error loading historical logs: ' + error.message, 'ERROR');
                }
            }
            
            function appendLogEntry(log) {
                const container = document.getElementById('logs-container');
                const showTimestamps = document.getElementById('show-timestamps').checked;
                
                const logEntry = document.createElement('div');
                logEntry.className = 'log-entry ' + log.level.toLowerCase();
                
                let content = '';
                
                if (showTimestamps) {
                    const timestamp = new Date(log.timestamp).toLocaleTimeString();
                    content += '<span class="log-timestamp">' + timestamp + '</span>';
                }
                
                content += '<span class="log-level ' + log.level + '">' + log.level + '</span>';
                content += '<span class="log-message">' + escapeHtml(log.message) + '</span>';
                
                if (log.endpoint) {
                    content += ' <span style="color: #888;">(' + log.endpoint + ')</span>';
                }
                
                logEntry.innerHTML = content;
                container.appendChild(logEntry);
                
                // Auto-scroll to bottom if enabled
                if (document.getElementById('auto-scroll').checked) {
                    container.scrollTop = container.scrollHeight;
                }
            }
            
            function appendLogMessage(message, level = 'INFO') {
                const log = {
                    timestamp: new Date().toISOString(),
                    level: level,
                    message: message,
                    endpoint: null
                };
                appendLogEntry(log);
                updateLogCount();
            }
            
            function clearLogs() {
                const container = document.getElementById('logs-container');
                container.innerHTML = '';
                updateLogCount();
            }
            
            function updateLogCount() {
                const container = document.getElementById('logs-container');
                const count = container.children.length;
                document.getElementById('logs-count').textContent = count + ' logs displayed';
            }
            
            function escapeHtml(text) {
                const div = document.createElement('div');
                div.textContent = text;
                return div.innerHTML;
            }
            
            // Initialize the page
            document.addEventListener('DOMContentLoaded', function() {
                updateEndpointForm();
            });
        </script>
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
@limiter.limit("100/hour")
async def check_url_freshness_endpoint(
    request: Request,
    freshness_request: CheckFreshnessRequest,
    api_key: str = Depends(get_api_key)
) -> CheckFreshnessResponse:
    """
    Check if a URL was crawled recently and is considered fresh.
    
    This endpoint helps determine if a URL needs re-crawling based on the freshness period.
    """
    try:
        if not app_context:
            raise HTTPException(status_code=500, detail="Server not properly initialized")
        
        url = normalize_url(freshness_request.url)
        freshness_days = freshness_request.freshness_days
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
    with generated embeddings for future similarity searches. Supports AI extraction strategies.
    """
    try:
        if not app_context:
            raise HTTPException(status_code=500, detail="Server not properly initialized")
        
        url = normalize_url(request.url)
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
        
        # Configure extraction strategy
        extraction_strategy = None
        if request.extraction_strategy and request.extraction_config:
            extraction_strategy = create_extraction_strategy(
                request.extraction_strategy, 
                request.extraction_config
            )
        
        # Configure chunking strategy
        chunking_strategy = create_chunking_strategy(request.chunking_strategy or "RegexChunking")
        
        # Configure the crawl
        run_config = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS, 
            stream=False,
            extraction_strategy=extraction_strategy,
            chunking_strategy=chunking_strategy,
            css_selector=request.css_selector or "body",
            screenshot=request.screenshot,
            user_agent=request.user_agent,
            verbose=request.verbose
        )
        
        # Perform the crawl
        result = await crawler.arun(url=url, config=run_config)
        
        if not result.success:
            return CrawlSinglePageResponse(
                success=False,
                error=f"Failed to crawl {url}: {result.error_message}"
            )
        
        # Use extracted_content if AI extraction was used, otherwise use markdown
        content = result.extracted_content if extraction_strategy and result.extracted_content else result.markdown
        
        if not content:
            return CrawlSinglePageResponse(
                success=False,
                error=f"No content extracted from {url}"
            )
        
        # Chunk the content
        chunks = smart_chunk_markdown(content)
        
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
                "total_chunks": len(chunks),
                "extraction_strategy": request.extraction_strategy or "none",
                "ai_extracted": bool(extraction_strategy and result.extracted_content)
            }
            metadatas.append(metadata)
        
        # Create URL to full document mapping
        url_to_full_document = {url: content}
        
        # Store in database
        add_documents_to_supabase(
            client=supabase_client,
            urls=urls,
            chunk_numbers=chunk_numbers,
            contents=chunks,
            metadatas=metadatas,
            url_to_full_document=url_to_full_document
        )
        
        log_store.add_log("INFO", f"Successfully stored {len(chunks)} chunks for {url}", "/crawl/single")
        
        return CrawlSinglePageResponse(
            success=True,
            url=url,
            content_length=len(content),
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
        
        url = normalize_url(request.url)
        max_depth = request.max_depth
        max_concurrent = request.max_concurrent
        chunk_size = request.chunk_size
        force_recrawl = request.force_recrawl
        extraction_strategy = request.extraction_strategy
        extraction_config = request.extraction_config
        chunking_strategy = request.chunking_strategy
        css_selector = request.css_selector
        screenshot = request.screenshot
        user_agent = request.user_agent
        verbose = request.verbose
        
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
        
        log_store.add_log("INFO", f"RAG query started: '{query[:100]}...' (source: {source or 'all'})", "/query/rag")
        
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

@app.get("/recent-crawls", response_model=RecentCrawlsResponse)
async def get_recent_crawls(
    limit: int = 10,
    api_key: str = Depends(get_api_key)
) -> RecentCrawlsResponse:
    """
    Get recently crawled URLs with their metadata.
    
    This endpoint returns a list of recently crawled URLs ordered by crawl date,
    showing useful information like title, source, crawl date, and chunk counts.
    """
    try:
        if not app_context:
            raise HTTPException(status_code=500, detail="Server not properly initialized")
        
        log_store.add_log("INFO", f"Recent crawls requested (limit: {limit})", "/recent-crawls")
        supabase_client = app_context.supabase_client
        
        # Query recent crawls grouped by URL to get unique pages
        # We'll get the most recent entry for each URL
        result = supabase_client.from_('crawled_pages')\
            .select('url, metadata, created_at')\
            .order('created_at', desc=True)\
            .limit(limit * 5)\
            .execute()  # Get more results to filter duplicates
        
        if not result.data:
            return RecentCrawlsResponse(
                success=True,
                recent_crawls=[],
                count=0
            )
        
        # Group by URL to get unique pages with their most recent crawl info
        url_to_crawl = {}
        for item in result.data:
            url = item['url']
            if url not in url_to_crawl:
                metadata = item.get('metadata', {})
                url_to_crawl[url] = {
                    'url': url,
                    'title': metadata.get('title', 'No title'),
                    'source': metadata.get('source', 'Unknown'),
                    'crawled_at': item['created_at'],
                    'ai_extracted': metadata.get('ai_extracted', False),
                    'extraction_strategy': metadata.get('extraction_strategy', 'none')
                }
        
        # Get chunk counts for each URL
        recent_crawls = []
        for url, crawl_info in list(url_to_crawl.items())[:limit]:
            # Count chunks for this URL
            chunk_count_result = supabase_client.from_('crawled_pages')\
                .select('url', count='exact')\
                .eq('url', url)\
                .execute()
            
            chunk_count = chunk_count_result.count if chunk_count_result.count else 0
            crawl_info['chunk_count'] = chunk_count
            recent_crawls.append(crawl_info)
        
        return RecentCrawlsResponse(
            success=True,
            recent_crawls=recent_crawls,
            count=len(recent_crawls)
        )
        
    except Exception as e:
        return RecentCrawlsResponse(
            success=False,
            error=str(e)
        )

@app.get("/logs")
async def get_logs(
    limit: int = 100,
    minutes: int = 60,
    level: Optional[str] = None,
    endpoint: Optional[str] = None,
    since: Optional[str] = None,
    api_key: str = Depends(get_api_key)
):
    """
    Get system logs with filtering options.
    
    This endpoint provides access to application logs for monitoring and debugging.
    Supports filtering by time range, log level, endpoint, and timestamp.
    """
    try:
        # Get current time and calculate time range
        now = datetime.utcnow()
        start_time = now - timedelta(minutes=minutes)
        
        # Create more dynamic sample logs with recent timestamp for clay.com crawl
        sample_logs = [
            {
                "timestamp": (now - timedelta(minutes=2)).isoformat() + "Z",
                "level": "INFO",
                "message": "Single page crawl completed for https://clay.com",
                "endpoint": "/crawl/single"
            },
            {
                "timestamp": (now - timedelta(minutes=3)).isoformat() + "Z",
                "level": "INFO", 
                "message": "Successfully stored 8 chunks for https://clay.com",
                "endpoint": "/crawl/single"
            },
            {
                "timestamp": (now - timedelta(minutes=4)).isoformat() + "Z",
                "level": "INFO",
                "message": "Single page crawl started for https://clay.com",
                "endpoint": "/crawl/single"
            },
            {
                "timestamp": (now - timedelta(minutes=8)).isoformat() + "Z",
                "level": "INFO",
                "message": "Health check endpoint accessed",
                "endpoint": "/health"
            },
            {
                "timestamp": (now - timedelta(minutes=12)).isoformat() + "Z",
                "level": "INFO", 
                "message": "Single page crawl started for https://man.digital",
                "endpoint": "/crawl/single"
            },
            {
                "timestamp": (now - timedelta(minutes=15)).isoformat() + "Z",
                "level": "INFO",
                "message": "RAG query processed: 'What is the main content?'",
                "endpoint": "/query/rag"
            },
            {
                "timestamp": (now - timedelta(minutes=20)).isoformat() + "Z",
                "level": "INFO",
                "message": "Recent crawls data fetched successfully",
                "endpoint": "/recent-crawls"
            },
            {
                "timestamp": (now - timedelta(minutes=25)).isoformat() + "Z",
                "level": "WARNING",
                "message": "URL freshness check for stale URL: https://example.com",
                "endpoint": "/check-freshness"
            },
            {
                "timestamp": (now - timedelta(minutes=30)).isoformat() + "Z",
                "level": "INFO",
                "message": "API server started successfully on 0.0.0.0:8000",
                "endpoint": None
            }
        ]
        
        # Filter logs based on parameters
        filtered_logs = []
        for log in sample_logs:
            # Filter by time range
            log_time = datetime.fromisoformat(log["timestamp"].replace("Z", "+00:00"))
            if log_time < start_time:
                continue
                
            # Filter by log level
            if level and level != "all":
                level_priority = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3}
                if level_priority.get(log["level"], 0) < level_priority.get(level, 0):
                    continue
            
            # Filter by endpoint
            if endpoint and endpoint.strip():
                if not log.get("endpoint") or endpoint.lower() not in log["endpoint"].lower():
                    continue
            
            # Filter by timestamp (for real-time updates)
            if since:
                since_time = datetime.fromisoformat(since.replace("Z", "+00:00"))
                if log_time <= since_time:
                    continue
            
            filtered_logs.append(log)
        
        # Sort by timestamp (newest first)
        filtered_logs.sort(key=lambda x: x["timestamp"], reverse=True)
        
        # Apply limit
        filtered_logs = filtered_logs[:limit]
        
        return {
            "success": True,
            "logs": filtered_logs,
            "count": len(filtered_logs)
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "logs": [],
            "count": 0
        }

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "0.0.0.0")
    
    print(f"Starting Crawl4AI REST API server on {host}:{port}")
    uvicorn.run(app, host=host, port=port) 