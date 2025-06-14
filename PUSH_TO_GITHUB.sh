#!/bin/bash

# GitHub Repository Setup Script for romeoman/crawl4ai-rest-api

echo "🚀 Setting up GitHub repository for Crawl4AI REST API..."

GITHUB_USERNAME="romeoman"
REPO_NAME="crawl4ai-rest-api"

echo "👤 GitHub Username: $GITHUB_USERNAME"
echo "📁 Repository Name: $REPO_NAME"
echo ""

# Check if remote already exists
if git remote get-url origin >/dev/null 2>&1; then
    echo "⚠️  Remote 'origin' already exists. Removing it first..."
    git remote remove origin
fi

echo "📡 Adding GitHub remote..."
git remote add origin https://github.com/$GITHUB_USERNAME/$REPO_NAME.git

echo "📁 Committing any remaining changes..."
git add .
git commit -m "Clean up repository and prepare for GitHub

🧹 Cleanup:
- Moved tests to tests/ directory
- Removed unnecessary test files and results
- Organized project structure

🎯 Repository Ready:
- All 22 tasks completed
- Production API deployed on Railway
- Comprehensive testing and documentation
- Security and monitoring features implemented

🚀 Live API: https://crawl4ai-production-9932.up.railway.app/

🤖 Generated with [Claude Code](https://claude.ai/code)

Co-Authored-By: Claude <noreply@anthropic.com>" || echo "No changes to commit"

echo "🚀 Pushing to GitHub..."
git push -u origin main

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Successfully pushed to GitHub!"
    echo "🔗 Repository URL: https://github.com/$GITHUB_USERNAME/$REPO_NAME"
    echo "🌐 Live API: https://crawl4ai-production-9932.up.railway.app/"
    echo "📚 API Docs: https://crawl4ai-production-9932.up.railway.app/docs"
    echo ""
    echo "🎯 Next steps:"
    echo "1. Visit your repository: https://github.com/$GITHUB_USERNAME/$REPO_NAME"
    echo "2. Add repository topics: fastapi, web-crawling, rag, railway, python, supabase"
    echo "3. Create a release tag for v1.0.0"
    echo "4. Star your repository! ⭐"
    echo "5. Share it with the community!"
else
    echo ""
    echo "❌ Failed to push to GitHub. Please check:"
    echo "1. Repository exists: https://github.com/$GITHUB_USERNAME/$REPO_NAME"
    echo "2. You have write access to the repository"
    echo "3. Your GitHub authentication is set up"
fi