# Tests

This directory contains test suites for the Crawl4AI REST API.

## Running Tests

### Comprehensive Test Suite
```bash
python tests/comprehensive_test.py
```

This runs the full production test suite against the deployed API.

### Local REST API Tests
```bash
python tests/test_rest_api.py
```

Unit tests for local development and testing.

## Test Coverage

The test suite covers:
- Authentication and authorization
- All API endpoints
- Error handling
- Performance benchmarks
- CORS and security features

**Current Success Rate**: 91.7% (11/12 tests passed)