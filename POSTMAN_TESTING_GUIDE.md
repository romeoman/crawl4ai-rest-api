# Crawl4AI REST API - Postman Testing Guide

## 🚀 Production Deployment Information

**Base URL:** `https://crawl4ai-production-9932.up.railway.app`  
**Authentication:** Bearer Token (see `API_CREDENTIALS.txt` for the key)  
**Content-Type:** `application/json`

---

## 📋 Postman Setup Instructions

### 1. Create New Collection
1. Open Postman
2. Click "New" → "Collection"
3. Name it: `Crawl4AI REST API - Production`
4. Add description: `Testing Crawl4AI FastAPI deployment on Railway`

### 2. Set Collection Variables
Go to your collection → Variables tab and add:

| Variable | Value | Description |
|----------|-------|-------------|
| `baseUrl` | `https://crawl4ai-production-9932.up.railway.app` | Production base URL |
| `apiKey` | `{{BEARER_TOKEN}}` | Reference to auth token |

### 3. Set Collection Authorization
1. Go to collection → Authorization tab
2. Type: `Bearer Token`
3. Token: `{{apiKey}}`

---

## 🔑 Authentication Setup

**Method:** Bearer Token Authentication  
**Header:** `Authorization: Bearer {{API_KEY}}`

> 📁 **API Key Location:** Check the `API_CREDENTIALS.txt` file for the actual bearer token value.

---

## 📡 API Endpoints

### 1. Health Check
**Purpose:** Verify API is running and accessible

```http
GET {{baseUrl}}/health
Authorization: Bearer {{apiKey}}
```

**Expected Response:**
```json
{
  "status": "healthy",
  "service": "Crawl4AI REST API"
}
```

---

### 2. Single URL Crawl
**Purpose:** Crawl a single webpage with specified options

```http
POST {{baseUrl}}/crawl/single
Authorization: Bearer {{apiKey}}
Content-Type: application/json
```

**Request Body (Basic Crawl - No AI):**
```json
{
  "url": "https://example.com",
  "force_recrawl": false
}
```

**Note about AI Extraction:** 
> ✅ **Now Fully Available!** The production FastAPI now supports LLM extraction strategies with multiple AI providers.
> 
> **Supported Features:** Multiple AI providers (OpenAI, Anthropic, Google, Custom models), Flexible chunking strategies, Intelligent content extraction, Enhanced metadata tracking
> **Your Custom Model:** Full support for `gpt-4.1-nano-2025-04-14` ✅

**Request Body (With AI Extraction - Now Available!):**
```json
{
  "url": "https://example.com",
  "extraction_strategy": "LLMExtractionStrategy",
  "extraction_config": {
    "provider": "google/gemini-2.5-flash-preview-05-20",
    "api_token": "your-api-key",
    "instruction": "Extract the main content and key information"
  },
  "chunking_strategy": "RegexChunking",
  "css_selector": "body",
  "screenshot": false,
  "user_agent": "Crawl4AI-Bot/1.0",
  "verbose": true
}
```

**Supported Provider Formats (When Implemented):**
- Google: `"google/gemini-2.5-flash-preview-05-20"` (Default)
- Custom models: `"gpt-4.1-nano-2025-04-14"` ✅ (Your current model)
- OpenAI: `"openai/gpt-4.1-nano-2025-04-14"`
- Anthropic: `"anthropic/claude-3-5-haiku-20241022"`

**Note:** ✅ **AI extraction is now fully supported!** Use the second request body format above to enable intelligent content extraction with your preferred AI model.

---

### 3. Smart Crawl (Multi-page)
**Purpose:** Intelligent crawling with link following and content discovery

```http
POST {{baseUrl}}/crawl/smart
Authorization: Bearer {{apiKey}}
Content-Type: application/json
```

**Request Body:**
```json
{
  "url": "https://example.com",
  "max_depth": 3,
  "max_concurrent": 10,
  "chunk_size": 5000,
  "force_recrawl": false
}
```

**Request Body (With AI Extraction):**
```json
{
  "url": "https://example.com",
  "max_depth": 3,
  "max_concurrent": 10,
  "chunk_size": 5000,
  "force_recrawl": false,
  "extraction_strategy": "LLMExtractionStrategy",
  "extraction_config": {
    "provider": "google/gemini-2.5-flash-preview-05-20",
    "api_token": "your-api-key",
    "instruction": "Extract the main content and key information from each page"
  },
  "chunking_strategy": "RegexChunking",
  "css_selector": "body",
  "screenshot": false,
  "user_agent": "Crawl4AI-Bot/1.0",
  "verbose": true
}
```

**Note:** LLM extraction parameters will be added when AI features are implemented.

---

### 4. RAG Query
**Purpose:** Query previously crawled and stored content using RAG (Retrieval-Augmented Generation)

```http
POST {{baseUrl}}/query/rag
Authorization: Bearer {{apiKey}}
Content-Type: application/json
```

**Request Body:**
```json
{
  "query": "What are the main features of this product?",
  "top_k": 5,
  "threshold": 0.7
}
```

---

### 5. Check URL Freshness
**Purpose:** Check if cached content for URLs is still fresh or needs re-crawling

```http
POST {{baseUrl}}/check-freshness
Authorization: Bearer {{apiKey}}
Content-Type: application/json
```

**Request Body:**
```json
{
  "urls": [
    "https://example.com",
    "https://another-site.com"
  ]
}
```

**Expected Response:**
```json
{
  "results": [
    {
      "url": "https://example.com",
      "is_fresh": true,
      "last_crawled": "2024-01-15T10:30:00Z",
      "days_old": 2
    },
    {
      "url": "https://another-site.com",
      "is_fresh": false,
      "last_crawled": "2024-01-01T09:00:00Z",
      "days_old": 35
    }
  ]
}
```

---

### 6. Get Sources
**Purpose:** Retrieve list of all crawled sources and their metadata

```http
GET {{baseUrl}}/sources
Authorization: Bearer {{apiKey}}
```

**Query Parameters (Optional):**
- `limit`: Number of results (default: 100)
- `offset`: Pagination offset (default: 0)
- `domain`: Filter by specific domain

**Example with parameters:**
```http
GET {{baseUrl}}/sources?limit=50&domain=example.com
Authorization: Bearer {{apiKey}}
```

---

### 7. Enhanced Playground Interface ✨
**Purpose:** Advanced web interface recreating the original Crawl4AI playground experience

```http
GET {{baseUrl}}/playground
```

**🎯 Features (Just Like the Original!):**
- **🧪 Interactive API Testing** - Real-time endpoint testing with dynamic forms
- **🗄️ Database Browser** - Browse crawled sources and content with table views
- **📊 System Monitoring** - Live status dashboard and configuration overview  
- **📚 Comprehensive Documentation** - Built-in API reference and examples
- **⚡ Live Request Generation** - Auto-generated cURL commands
- **🔄 Real-time Responses** - Instant feedback with formatted JSON responses

**🚀 Getting Started:**
1. Open `https://crawl4ai-production-9932.up.railway.app/playground` in your browser
2. Navigate between tabs: **API Testing** | **Database Browser** | **Monitoring** | **Documentation**
3. Select an endpoint from the dropdown in the API Testing tab
4. Fill in the dynamic form fields (auto-generated based on endpoint)
5. Click "Execute Request" to see real-time results
6. Use the Database Browser to explore crawled content
7. Copy generated cURL commands for your own applications

**💡 Pro Tips:**
- **Database Browser** → Click "Refresh Sources" to see all crawled domains
- **Click "Query" next to any source** → Auto-fills RAG query for that domain
- **API Testing** → All forms are dynamic and validate input in real-time
- **Monitoring Tab** → Check system status and current limitations
- **Generated cURL** → Updates automatically as you change form inputs

> ✅ **Fully Operational:** This enhanced playground recreates the **original advanced Crawl4AI playground** functionality!
> 
> **Perfect for:** Testing, development, database exploration, API discovery, and generating integration code

---

## 🧪 Testing Scenarios

### Scenario 1: Basic Health Check
1. **Goal:** Verify API is operational
2. **Request:** `GET /health`
3. **Expected:** 200 OK with health status

### Scenario 2: Simple Website Crawl
1. **Goal:** Crawl a simple webpage
2. **Request:** `POST /crawl/single` with `{"url": "https://httpbin.org/html"}`
3. **Expected:** 200 OK with extracted content

### Scenario 3: E-commerce Smart Crawl
1. **Goal:** Crawl product pages intelligently
2. **Request:** `POST /crawl/smart` with e-commerce URL and product extraction
3. **Expected:** Multiple pages crawled with product data

### Scenario 4: RAG Knowledge Query
1. **Goal:** Query previously crawled content
2. **Setup:** First crawl some content, then query it
3. **Request:** `POST /query/rag` with relevant question
4. **Expected:** AI-generated answer based on crawled content

### Scenario 5: Content Freshness Management
1. **Goal:** Check if content needs re-crawling
2. **Request:** `POST /check-freshness` with list of URLs
3. **Expected:** Freshness status for each URL

---

## 🚨 Error Responses

### 401 Unauthorized
```json
{
  "detail": "Invalid or missing API key"
}
```
**Solution:** Check your Bearer token in the Authorization header

### 422 Validation Error
```json
{
  "detail": [
    {
      "loc": ["body", "url"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```
**Solution:** Check required fields in request body

### 500 Internal Server Error
```json
{
  "detail": "Crawling failed: [specific error message]"
}
```
**Solution:** Check URL accessibility and crawler configuration

---

## 📊 Performance Notes

- **Timeout:** Requests may take 30-120 seconds for complex crawls
- **Rate Limiting:** No specific limits, but be reasonable
- **Caching:** Content cached for 30 days by default
- **Concurrent Requests:** Supported, but crawler is resource-intensive

---

## 🔧 Environment Configuration

The production API is configured with:
- **Freshness Period:** 30 days
- **Default Browser:** Chromium (headless)
- **Database:** Supabase PostgreSQL with vector embeddings
- **AI Models:** Supports OpenAI, Anthropic, Google, etc.

---

## 📝 Notes for Testing

1. **Start with Health Check:** Always verify API connectivity first
2. **Use Simple URLs First:** Test with reliable sites like `httpbin.org` or `example.com`
3. **Check Logs:** Monitor Railway logs if requests fail
4. **API Key Security:** Never commit the API key to version control
5. **Timeout Handling:** Some crawls take time - set appropriate timeouts in Postman

---

## 🆘 Troubleshooting

### Common Issues:
1. **"Invalid API key"** → Check `API_CREDENTIALS.txt` for correct token
2. **"URL not accessible"** → Verify target URL works in browser
3. **"Extraction failed"** → Check extraction strategy configuration
4. **"Database error"** → Supabase connection issue (should auto-resolve)

### Getting Help:
- Check Railway logs: `railway logs`
- Verify environment variables: `railway variables`
- Test locally first: `python test_rest_api.py`

---

*Generated for Crawl4AI REST API Production Deployment*  
*Railway URL: https://crawl4ai-production-9932.up.railway.app* 