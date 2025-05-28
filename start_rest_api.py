#!/usr/bin/env python3
"""
Startup script for Railway deployment - runs the FastAPI REST API
"""
import os
import sys
import uvicorn

def main():
    # Get port from Railway environment (defaults to 8000 for local)
    port = int(os.getenv('PORT', 8000))
    host = os.getenv('HOST', '0.0.0.0')
    
    print(f"Starting Crawl4AI REST API on {host}:{port}")
    
    # Run the FastAPI app
    uvicorn.run(
        "src.rest_api:app",
        host=host,
        port=port,
        log_level="info",
        access_log=True
    )

if __name__ == "__main__":
    main() 