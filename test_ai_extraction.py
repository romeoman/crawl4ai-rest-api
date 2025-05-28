#!/usr/bin/env python3
"""
Test script for AI extraction capabilities in the Crawl4AI REST API.
Tests both single page crawl and smart crawl with AI extraction.
"""

import requests
import json
import sys

# Configuration
BASE_URL = "https://crawl4ai-production-9932.up.railway.app"
API_KEY = "secure-crawl4ai-bearer-token-2024"

def test_health():
    """Test the health endpoint."""
    print("🏥 Testing health endpoint...")
    response = requests.get(
        f"{BASE_URL}/health",
        headers={"Authorization": f"Bearer {API_KEY}"}
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    return response.status_code == 200

def test_ai_extraction_single():
    """Test single page crawl with AI extraction."""
    print("\n🤖 Testing AI extraction on single page...")
    
    # Test data - using a simple test page
    test_data = {
        "url": "https://httpbin.org/html",
        "extraction_strategy": "LLMExtractionStrategy",
        "extraction_config": {
            "provider": "gpt-4.1-nano-2025-04-14",
            "instruction": "Extract the main HTML elements and their content structure"
        },
        "chunking_strategy": "RegexChunking",
        "force_recrawl": True,
        "verbose": True
    }
    
    print(f"Request data: {json.dumps(test_data, indent=2)}")
    
    response = requests.post(
        f"{BASE_URL}/crawl/single",
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        },
        json=test_data
    )
    
    print(f"Status: {response.status_code}")
    result = response.json()
    print(f"Response: {json.dumps(result, indent=2)}")
    
    # Check if the request was successful
    if response.status_code == 200 and result.get("success"):
        print("✅ AI extraction test completed successfully!")
        return True
    else:
        print("❌ AI extraction test failed!")
        return False

def test_playground_ai_forms():
    """Test that the playground includes AI extraction forms."""
    print("\n🎪 Testing playground AI extraction forms...")
    
    response = requests.get(f"{BASE_URL}/playground")
    html_content = response.text
    
    # Check for AI extraction form elements
    ai_elements = [
        "🤖 AI Extraction (Optional)",
        "Enable AI Content Extraction",
        "gpt-4.1-nano-2025-04-14",
        "Extraction Instruction",
        "Chunking Strategy"
    ]
    
    all_found = True
    for element in ai_elements:
        if element in html_content:
            print(f"✅ Found: {element}")
        else:
            print(f"❌ Missing: {element}")
            all_found = False
    
    return all_found

def test_basic_crawl():
    """Test basic crawl without AI extraction for comparison."""
    print("\n🕷️ Testing basic crawl (no AI)...")
    
    test_data = {
        "url": "https://httpbin.org/html",
        "force_recrawl": True
    }
    
    response = requests.post(
        f"{BASE_URL}/crawl/single",
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        },
        json=test_data
    )
    
    print(f"Status: {response.status_code}")
    result = response.json()
    
    if response.status_code == 200 and result.get("success"):
        print("✅ Basic crawl test completed successfully!")
        print(f"Content length: {result.get('content_length', 0)} chars")
        print(f"Chunks stored: {result.get('chunks_stored', 0)}")
        return True
    else:
        print("❌ Basic crawl test failed!")
        print(f"Error: {result.get('error', 'Unknown error')}")
        return False

def main():
    """Run all tests."""
    print("🚀 Starting AI Extraction Tests for Crawl4AI REST API")
    print("=" * 60)
    
    tests = [
        ("Health Check", test_health),
        ("Basic Crawl", test_basic_crawl), 
        ("Playground AI Forms", test_playground_ai_forms),
        ("AI Extraction Single Page", test_ai_extraction_single),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 TEST RESULTS SUMMARY")
    print("=" * 60)
    
    passed = 0
    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{test_name:<30} {status}")
        if result:
            passed += 1
    
    print(f"\n🎯 Overall: {passed}/{len(results)} tests passed")
    
    if passed == len(results):
        print("🎉 All tests passed! AI extraction is fully operational!")
        return 0
    else:
        print("⚠️ Some tests failed. Check the output above for details.")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 