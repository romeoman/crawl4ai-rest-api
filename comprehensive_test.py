#!/usr/bin/env python3
"""
Comprehensive test suite for the Crawl4AI REST API deployed on Railway.
"""
import requests
import json
import time
from datetime import datetime
from typing import Dict, Any, List

# Configuration
BASE_URL = "https://crawl4ai-production-9932.up.railway.app"
API_KEY = "secure-crawl4ai-bearer-token-2024"
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

class APITester:
    def __init__(self):
        self.results: List[Dict[str, Any]] = []
        self.passed = 0
        self.failed = 0
    
    def test(self, name: str, func, *args, **kwargs):
        """Run a test and record results."""
        print(f"\n🧪 Testing: {name}")
        start_time = time.time()
        
        try:
            result = func(*args, **kwargs)
            duration = time.time() - start_time
            
            if result.get("success", True):
                print(f"✅ PASSED ({duration:.2f}s)")
                self.passed += 1
                status = "PASSED"
            else:
                print(f"❌ FAILED ({duration:.2f}s): {result.get('error', 'Unknown error')}")
                self.failed += 1
                status = "FAILED"
                
        except Exception as e:
            duration = time.time() - start_time
            print(f"💥 ERROR ({duration:.2f}s): {str(e)}")
            self.failed += 1
            status = "ERROR"
            result = {"error": str(e)}
        
        self.results.append({
            "name": name,
            "status": status,
            "duration": duration,
            "result": result,
            "timestamp": datetime.now().isoformat()
        })
        
        return result
    
    def summary(self):
        """Print test summary."""
        total = self.passed + self.failed
        print(f"\n📊 TEST SUMMARY")
        print(f"{'='*50}")
        print(f"Total Tests: {total}")
        print(f"Passed: {self.passed} ({(self.passed/total*100):.1f}%)" if total > 0 else "Passed: 0")
        print(f"Failed: {self.failed} ({(self.failed/total*100):.1f}%)" if total > 0 else "Failed: 0")
        print(f"{'='*50}")
        
        # Failed tests details
        if self.failed > 0:
            print(f"\n❌ FAILED TESTS:")
            for result in self.results:
                if result["status"] in ["FAILED", "ERROR"]:
                    print(f"  - {result['name']}: {result['result'].get('error', 'Unknown error')}")
    
    def export_results(self, filename: str = "test_results.json"):
        """Export test results to JSON file."""
        with open(filename, 'w') as f:
            json.dump({
                "summary": {
                    "total": self.passed + self.failed,
                    "passed": self.passed,
                    "failed": self.failed,
                    "timestamp": datetime.now().isoformat()
                },
                "results": self.results
            }, f, indent=2)
        print(f"\n📄 Results exported to {filename}")

def test_health_endpoint():
    """Test the health check endpoint."""
    response = requests.get(f"{BASE_URL}/health")
    
    if response.status_code != 200:
        return {"success": False, "error": f"Status code: {response.status_code}"}
    
    data = response.json()
    if data.get("status") != "healthy":
        return {"success": False, "error": f"Unexpected status: {data.get('status')}"}
    
    return {"success": True, "status_code": response.status_code, "data": data}

def test_authentication_required():
    """Test that protected endpoints require authentication."""
    response = requests.get(f"{BASE_URL}/sources")
    
    if response.status_code != 401:
        return {"success": False, "error": f"Expected 401, got {response.status_code}"}
    
    return {"success": True, "status_code": response.status_code}

def test_invalid_authentication():
    """Test invalid API key handling."""
    headers = {"Authorization": "Bearer invalid-key"}
    response = requests.get(f"{BASE_URL}/sources", headers=headers)
    
    if response.status_code != 401:
        return {"success": False, "error": f"Expected 401, got {response.status_code}"}
    
    return {"success": True, "status_code": response.status_code}

def test_sources_endpoint():
    """Test the sources listing endpoint."""
    response = requests.get(f"{BASE_URL}/sources", headers=HEADERS)
    
    if response.status_code != 200:
        return {"success": False, "error": f"Status code: {response.status_code}"}
    
    data = response.json()
    if "sources" not in data:
        return {"success": False, "error": "Missing 'sources' field in response"}
    
    return {"success": True, "status_code": response.status_code, "data": data}

def test_url_freshness_check():
    """Test URL freshness checking."""
    payload = {"url": "https://example.com"}
    response = requests.post(f"{BASE_URL}/check-freshness", headers=HEADERS, json=payload)
    
    if response.status_code != 200:
        return {"success": False, "error": f"Status code: {response.status_code}"}
    
    data = response.json()
    required_fields = ["success", "url", "is_fresh"]
    for field in required_fields:
        if field not in data:
            return {"success": False, "error": f"Missing field: {field}"}
    
    return {"success": True, "status_code": response.status_code, "data": data}

def test_single_page_crawl():
    """Test single page crawling."""
    payload = {"url": "https://httpbin.org/html", "max_pages": 1}
    response = requests.post(f"{BASE_URL}/crawl/single", headers=HEADERS, json=payload)
    
    if response.status_code != 200:
        return {"success": False, "error": f"Status code: {response.status_code}"}
    
    data = response.json()
    if not data.get("success"):
        return {"success": False, "error": data.get("error", "Crawl failed")}
    
    required_fields = ["success", "url", "content_length"]
    for field in required_fields:
        if field not in data:
            return {"success": False, "error": f"Missing field: {field}"}
    
    return {"success": True, "status_code": response.status_code, "data": data}

def test_smart_crawl():
    """Test smart crawling with multiple pages."""
    payload = {"url": "https://httpbin.org/", "max_pages": 2}
    response = requests.post(f"{BASE_URL}/crawl/smart", headers=HEADERS, json=payload)
    
    if response.status_code != 200:
        return {"success": False, "error": f"Status code: {response.status_code}"}
    
    data = response.json()
    if not data.get("success"):
        return {"success": False, "error": data.get("error", "Smart crawl failed")}
    
    return {"success": True, "status_code": response.status_code, "data": data}

def test_rag_query():
    """Test RAG query functionality."""
    payload = {
        "query": "What is the main content?",
        "max_results": 3
    }
    response = requests.post(f"{BASE_URL}/query/rag", headers=HEADERS, json=payload)
    
    if response.status_code != 200:
        return {"success": False, "error": f"Status code: {response.status_code}"}
    
    data = response.json()
    required_fields = ["success", "query", "results"]
    for field in required_fields:
        if field not in data:
            return {"success": False, "error": f"Missing field: {field}"}
    
    return {"success": True, "status_code": response.status_code, "data": data}

def test_playground_endpoint():
    """Test the playground HTML interface."""
    response = requests.get(f"{BASE_URL}/playground")
    
    if response.status_code != 200:
        return {"success": False, "error": f"Status code: {response.status_code}"}
    
    if "text/html" not in response.headers.get("content-type", ""):
        return {"success": False, "error": "Response is not HTML"}
    
    if "Crawl4AI" not in response.text:
        return {"success": False, "error": "HTML content doesn't contain expected title"}
    
    return {"success": True, "status_code": response.status_code, "content_length": len(response.text)}

def test_404_handling():
    """Test 404 error handling for non-existent endpoints."""
    response = requests.get(f"{BASE_URL}/nonexistent-endpoint")
    
    if response.status_code != 404:
        return {"success": False, "error": f"Expected 404, got {response.status_code}"}
    
    return {"success": True, "status_code": response.status_code}

def test_invalid_json():
    """Test handling of invalid JSON in POST requests."""
    headers = HEADERS.copy()
    response = requests.post(
        f"{BASE_URL}/check-freshness", 
        headers=headers, 
        data="invalid json"
    )
    
    if response.status_code not in [400, 422]:
        return {"success": False, "error": f"Expected 400/422, got {response.status_code}"}
    
    return {"success": True, "status_code": response.status_code}

def test_cors_headers():
    """Test CORS headers are present."""
    response = requests.options(f"{BASE_URL}/health")
    
    cors_headers = [
        "access-control-allow-origin",
        "access-control-allow-methods",
        "access-control-allow-headers"
    ]
    
    missing_headers = []
    for header in cors_headers:
        if header not in response.headers:
            missing_headers.append(header)
    
    if missing_headers:
        return {"success": False, "error": f"Missing CORS headers: {missing_headers}"}
    
    return {"success": True, "status_code": response.status_code, "cors_headers": cors_headers}

def main():
    """Run all tests."""
    print("🚀 Starting Comprehensive API Tests")
    print(f"Base URL: {BASE_URL}")
    print(f"API Key: {API_KEY[:20]}...")
    
    tester = APITester()
    
    # Basic functionality tests
    tester.test("Health Check", test_health_endpoint)
    tester.test("Authentication Required", test_authentication_required)
    tester.test("Invalid Authentication", test_invalid_authentication)
    tester.test("Sources Endpoint", test_sources_endpoint)
    tester.test("URL Freshness Check", test_url_freshness_check)
    
    # Crawling tests
    tester.test("Single Page Crawl", test_single_page_crawl)
    tester.test("Smart Crawl", test_smart_crawl)
    tester.test("RAG Query", test_rag_query)
    
    # Interface tests
    tester.test("Playground Endpoint", test_playground_endpoint)
    
    # Error handling tests
    tester.test("404 Handling", test_404_handling)
    tester.test("Invalid JSON Handling", test_invalid_json)
    tester.test("CORS Headers", test_cors_headers)
    
    # Print summary
    tester.summary()
    tester.export_results()

if __name__ == "__main__":
    main()