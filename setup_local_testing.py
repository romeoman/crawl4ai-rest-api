#!/usr/bin/env python3
"""
Setup script for local testing of Crawl4AI MCP Server
"""
import os
import sys
import subprocess
from pathlib import Path

def check_python_version():
    """Check if Python version is 3.12 or higher."""
    if sys.version_info < (3, 12):
        print("❌ Python 3.12 or higher is required.")
        print(f"Current version: {sys.version}")
        return False
    print(f"✅ Python version: {sys.version}")
    return True

def install_dependencies():
    """Install project dependencies."""
    print("\n📦 Installing dependencies...")
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "-e", "."], check=True)
        print("✅ Dependencies installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install dependencies: {e}")
        return False

def create_env_file():
    """Create .env file if it doesn't exist."""
    env_file = Path(".env")
    if env_file.exists():
        print("✅ .env file already exists")
        return True
    
    print("\n📝 Creating .env file...")
    env_content = """# Environment variables for Crawl4AI MCP Server local testing
# Copy this file to .env and fill in your actual values

# Required: OpenAI API key for embeddings
OPENAI_API_KEY=your_openai_api_key_here

# Required: Supabase configuration
SUPABASE_URL=your_supabase_project_url_here
SUPABASE_SERVICE_KEY=your_supabase_service_key_here

# Optional: Model choice for contextual embeddings (if not set, will use basic embeddings)
MODEL_CHOICE=gpt-4o-mini

# Optional: Port for local server (defaults to 11235)
PORT=11235

# Optional: Host for local server (defaults to 0.0.0.0)
HOST=0.0.0.0
"""
    
    try:
        env_file.write_text(env_content)
        print("✅ .env file created. Please edit it with your actual API keys.")
        return True
    except Exception as e:
        print(f"❌ Failed to create .env file: {e}")
        return False

def check_browser_setup():
    """Check if playwright browsers are installed."""
    print("\n🌐 Checking browser setup...")
    try:
        subprocess.run(["playwright", "install", "--help"], 
                      capture_output=True, check=True)
        print("✅ Playwright is available")
        
        # Check if browsers are installed
        print("Installing browsers (this may take a while)...")
        subprocess.run(["playwright", "install", "--with-deps"], check=True)
        print("✅ Browsers installed successfully")
        return True
    except subprocess.CalledProcessError:
        print("⚠️  Playwright not found. Installing...")
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "playwright"], check=True)
            subprocess.run(["playwright", "install", "--with-deps"], check=True)
            print("✅ Playwright and browsers installed")
            return True
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to install playwright: {e}")
            return False

def main():
    """Main setup function."""
    print("🚀 Setting up Crawl4AI MCP Server for local testing\n")
    
    # Check Python version
    if not check_python_version():
        return False
    
    # Install dependencies
    if not install_dependencies():
        return False
    
    # Create .env file
    if not create_env_file():
        return False
    
    # Check browser setup
    if not check_browser_setup():
        return False
    
    print("\n🎉 Setup complete!")
    print("\nNext steps:")
    print("1. Edit the .env file with your actual API keys")
    print("2. Run the server: cd src && python crawl4ai_mcp.py")
    print("3. Test the tools using the examples in LOCAL_TESTING_GUIDE.md")
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 