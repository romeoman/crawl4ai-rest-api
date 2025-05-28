#!/usr/bin/env python3
"""
Test script for Crawl4AI REST API endpoints
"""
import requests
import json
import time
import sys
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# API base URL
BASE_URL = "http://localhost:8000"

# Test API key (you can set this in your .env file)
API_KEY = os.getenv("CRAWL4AI_API_KEY", "test-api-key-123")

def get_headers(include_auth=True):
    """Get headers for API requests."""
    headers = {"Content-Type": "application/json"}
    if include_auth and API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"
    return headers

def test_health_endpoint():
    """Test the health check endpoint."""
    print("🔍 Testing /health endpoint...")
    try:
        response = requests.get(f"{BASE_URL}/health")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Health check passed: {data}")
            return True
        else:
            print(f"❌ Health check failed with status: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Health check failed with error: {e}")
        return False

def test_authentication():
    """Test authentication with and without API key."""
    print("\n🔍 Testing authentication...")
    
    # Test without API key (should fail if API key is required)
    try:
        response = requests.get(f"{BASE_URL}/sources")
        if response.status_code == 401:
            print("✅ Authentication properly required (401 without API key)")
        elif response.status_code == 200:
            print("✅ No authentication required (backward compatibility)")
        else:
            print(f"⚠️ Unexpected status without API key: {response.status_code}")
    except Exception as e:
        print(f"❌ Authentication test failed: {e}")
        return False
    
    # Test with API key
    try:
        response = requests.get(f"{BASE_URL}/sources", headers=get_headers())
        if response.status_code == 200:
            print("✅ Authentication successful with API key")
            return True
        else:
            print(f"❌ Authentication failed with API key: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Authentication with API key failed: {e}")
        return False

def test_check_freshness():
    """Test the check freshness endpoint."""
    print("\n🔍 Testing POST /check-freshness endpoint...")
    try:
        payload = {
            "url": "https://example.com",
            "freshness_days": 30
        }
        
        response = requests.post(
            f"{BASE_URL}/check-freshness",
            json=payload,
            headers=get_headers()
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                print(f"✅ Freshness check successful:")
                print(f"   URL: {data.get('url')}")
                print(f"   Is fresh: {data.get('is_fresh')}")
                print(f"   Last crawled: {data.get('last_crawled')}")
                print(f"   Days since crawl: {data.get('days_since_crawl')}")
                return True
            else:
                print(f"❌ Freshness check failed: {data.get('error')}")
                return False
        else:
            print(f"❌ Freshness check failed with status: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Freshness check failed with error: {e}")
        return False

def test_crawl_single_page():
    """Test the single page crawling endpoint."""
    print("\n🔍 Testing POST /crawl/single endpoint...")
    try:
        payload = {
            "url": "https://httpbin.org/json",
            "force_recrawl": False
        }
        
        response = requests.post(
            f"{BASE_URL}/crawl/single",
            json=payload,
            headers=get_headers()
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                print(f"✅ Single page crawl successful:")
                print(f"   URL: {data.get('url')}")
                print(f"   Content length: {data.get('content_length')}")
                print(f"   Chunks stored: {data.get('chunks_stored')}")
                print(f"   Was fresh: {data.get('was_fresh')}")
                print(f"   Last crawled: {data.get('last_crawled')}")
                return True
            else:
                print(f"❌ Single page crawl failed: {data.get('error')}")
                return False
        else:
            print(f"❌ Single page crawl failed with status: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Single page crawl failed with error: {e}")
        return False

def test_crawl_single_page_force():
    """Test the single page crawling endpoint with force_recrawl."""
    print("\n🔍 Testing POST /crawl/single endpoint with force_recrawl...")
    try:
        payload = {
            "url": "https://httpbin.org/json",
            "force_recrawl": True
        }
        
        response = requests.post(
            f"{BASE_URL}/crawl/single",
            json=payload,
            headers=get_headers()
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                print(f"✅ Force recrawl successful:")
                print(f"   URL: {data.get('url')}")
                print(f"   Content length: {data.get('content_length')}")
                print(f"   Chunks stored: {data.get('chunks_stored')}")
                print(f"   Was fresh: {data.get('was_fresh')}")
                return True
            else:
                print(f"❌ Force recrawl failed: {data.get('error')}")
                return False
        else:
            print(f"❌ Force recrawl failed with status: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Force recrawl failed with error: {e}")
        return False

def test_get_sources():
    """Test the get sources endpoint."""
    print("\n🔍 Testing GET /sources endpoint...")
    try:
        response = requests.get(f"{BASE_URL}/sources", headers=get_headers())
        
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                print(f"✅ Get sources successful:")
                print(f"   Available sources: {data.get('sources', [])}")
                print(f"   Source count: {data.get('count')}")
                return True
            else:
                print(f"❌ Get sources failed: {data.get('error')}")
                return False
        else:
            print(f"❌ Get sources failed with status: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Get sources failed with error: {e}")
        return False

def test_rag_query():
    """Test the RAG query endpoint."""
    print("\n🔍 Testing POST /query/rag endpoint...")
    try:
        payload = {
            "query": "json data",
            "match_count": 3
        }
        
        response = requests.post(
            f"{BASE_URL}/query/rag",
            json=payload,
            headers=get_headers()
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                print(f"✅ RAG query successful:")
                print(f"   Query: {data.get('query')}")
                print(f"   Results count: {data.get('count')}")
                if data.get('results'):
                    for i, result in enumerate(data['results'][:2]):
                        print(f"   Result {i+1}: {result.get('url')}")
                        print(f"   Similarity: {result.get('similarity')}")
                return True
            else:
                print(f"❌ RAG query failed: {data.get('error')}")
                return False
        else:
            print(f"❌ RAG query failed with status: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ RAG query failed with error: {e}")
        return False

def test_smart_crawl():
    """Test the smart crawl endpoint."""
    print("\n🔍 Testing POST /crawl/smart endpoint...")
    test_smart = input("Test smart crawl? This takes longer (y/N): ").strip().lower()
    
    if test_smart != 'y':
        print("⏭️ Skipping smart crawl test")
        return True
        
    try:
        payload = {
            "url": "https://httpbin.org/html",
            "max_depth": 1,
            "max_concurrent": 3,
            "chunk_size": 5000,
            "force_recrawl": False
        }
        
        response = requests.post(
            f"{BASE_URL}/crawl/smart",
            json=payload,
            headers=get_headers()
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                print(f"✅ Smart crawl successful:")
                print(f"   URL: {data.get('url')}")
                print(f"   Crawl type: {data.get('crawl_type')}")
                print(f"   Pages crawled: {data.get('pages_crawled')}")
                print(f"   Chunks stored: {data.get('chunks_stored')}")
                print(f"   Skipped fresh URLs: {data.get('skipped_fresh_urls')}")
                return True
            else:
                print(f"❌ Smart crawl failed: {data.get('error')}")
                return False
        else:
            print(f"❌ Smart crawl failed with status: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Smart crawl failed with error: {e}")
        return False

def main():
    """Main test function."""
    print("🔍 Crawl4AI REST API Tests")
    print("=" * 40)
    print(f"Testing API at: {BASE_URL}")
    print(f"Using API Key: {API_KEY[:10] + '...' if len(API_KEY) > 10 else API_KEY}")
    print()
    
    # Wait for user to start the server
    input("Please start the REST API server in another terminal (cd src && python rest_api.py) and press Enter to continue...")
    
    # Give the server a moment to start
    time.sleep(2)
    
    # Run tests
    tests = [
        ("Health Check", test_health_endpoint),
        ("Authentication", test_authentication),
        ("Check Freshness", test_check_freshness),
        ("Crawl Single Page", test_crawl_single_page),
        ("Force Recrawl", test_crawl_single_page_force),
        ("Get Sources", test_get_sources),
        ("RAG Query", test_rag_query),
        ("Smart Crawl", test_smart_crawl),
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n{'='*50}")
        print(f"Running: {test_name}")
        print('='*50)
        result = test_func()
        results.append((test_name, result))
        
        if not result:
            print(f"\n❌ Test '{test_name}' failed. Stopping tests.")
            break
        
        time.sleep(1)  # Brief pause between tests
    
    # Summary
    print(f"\n{'='*50}")
    print("TEST SUMMARY")
    print('='*50)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{test_name}: {status}")
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! Your REST API is working correctly.")
        print("\nAvailable endpoints:")
        print("- GET  /health              - Health check")
        print("- POST /check-freshness     - Check URL freshness")
        print("- POST /crawl/single        - Crawl a single page")
        print("- POST /crawl/smart         - Smart crawl with auto-detection")
        print("- GET  /sources             - Get available sources")
        print("- POST /query/rag           - Perform RAG query")
        print("\nAuthentication: Bearer token in Authorization header")
        print("URL Freshness: 30-day default freshness period")
        print("\nYou can also view the interactive API docs at: http://localhost:8000/docs")
    else:
        print(f"\n❌ {total - passed} test(s) failed. Please check the errors above.")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 