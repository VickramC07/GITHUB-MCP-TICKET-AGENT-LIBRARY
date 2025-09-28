#!/bin/bash

# TicketWatcher Installation Script (Fixed Version)
# This script sets up TicketWatcher with all the latest fixes

set -e

echo "🚀 Installing TicketWatcher (Fixed Version)..."

# Create ticketer directory
mkdir -p ticketer
cd ticketer

# Create the Python package structure
mkdir -p src/ticketwatcher

# Copy the source files from the FIXED version
echo "📁 Copying source files (with all fixes)..."

# Always download from the VickramC07 fork with latest fixes
echo "📥 Downloading from VickramC07/GITHUB-MCP-TICKET-AGENT-LIBRARY (latest fixes)..."
curl -sSL https://raw.githubusercontent.com/VickramC07/GITHUB-MCP-TICKET-AGENT-LIBRARY/main/src/ticketwatcher/__init__.py > src/ticketwatcher/__init__.py
curl -sSL https://raw.githubusercontent.com/VickramC07/GITHUB-MCP-TICKET-AGENT-LIBRARY/main/src/ticketwatcher/__main__.py > src/ticketwatcher/__main__.py
curl -sSL https://raw.githubusercontent.com/VickramC07/GITHUB-MCP-TICKET-AGENT-LIBRARY/main/src/ticketwatcher/cli.py > src/ticketwatcher/cli.py
curl -sSL https://raw.githubusercontent.com/VickramC07/GITHUB-MCP-TICKET-AGENT-LIBRARY/main/src/ticketwatcher/github_api.py > src/ticketwatcher/github_api.py
curl -sSL https://raw.githubusercontent.com/VickramC07/GITHUB-MCP-TICKET-AGENT-LIBRARY/main/src/ticketwatcher/agent_llm.py > src/ticketwatcher/agent_llm.py
curl -sSL https://raw.githubusercontent.com/VickramC07/GITHUB-MCP-TICKET-AGENT-LIBRARY/main/src/ticketwatcher/handlers.py > src/ticketwatcher/handlers.py
curl -sSL https://raw.githubusercontent.com/VickramC07/GITHUB-MCP-TICKET-AGENT-LIBRARY/main/requirements.txt > requirements.txt

# Create GitHub Actions workflow (outside ticketer folder)
echo "⚙️ Creating GitHub Actions workflow..."
cd ..
mkdir -p .github/workflows
cat > .github/workflows/ticket-agent.yml << 'EOF'
name: Ticket Agent
on:
  issues:
    types: [opened, labeled, reopened]
  issue_comment:
    types: [created]
jobs:
  agent:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.9'
      - name: Install dependencies
        run: |
          cd ticketer
          pip install -r requirements.txt
      - name: Run Ticket Agent
        run: |
          cd ticketer
          python run_ticketwatcher.py
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GITHUB_REPOSITORY: ${{ github.repository }}
          GITHUB_WORKSPACE: ${{ github.workspace }}
          TICKETWATCHER_MODEL: ${{ secrets.TICKETWATCHER_MODEL || 'gpt-4o-mini' }}
          ALLOWED_PATHS: ${{ secrets.ALLOWED_PATHS || 'src/,app/,calculator/' }}
          MAX_FILES: ${{ secrets.MAX_FILES || '4' }}
          MAX_LINES: ${{ secrets.MAX_LINES || '200' }}
          TICKETWATCHER_TRIGGER_LABELS: ${{ secrets.TICKETWATCHER_TRIGGER_LABELS || 'agent-fix,auto-pr' }}
          DEFAULT_AROUND_LINES: ${{ secrets.DEFAULT_AROUND_LINES || '60' }}
          TICKETWATCHER_BASE_BRANCH: ${{ secrets.TICKETWATCHER_BASE_BRANCH || 'main' }}
          TICKETWATCHER_BRANCH_PREFIX: ${{ secrets.TICKETWATCHER_BRANCH_PREFIX || 'agent-fix/' }}
EOF

# Go back to ticketer directory and create runner script
cd ticketer

# Create a simple runner script that handles imports correctly
cat > run_ticketwatcher.py << 'EOF'
#!/usr/bin/env python3
"""
TicketWatcher runner script
Handles imports correctly when running from the ticketer directory
"""
import sys
import os

# Add the src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Now we can import the modules
from ticketwatcher.cli import main

if __name__ == "__main__":
    main()
EOF

chmod +x run_ticketwatcher.py

# Create a simple README for the ticketer folder
cat > README.md << 'EOF'
# TicketWatcher (Fixed Version)

Automated GitHub issue fixer using AI - with all the latest fixes!

## What's Fixed ✅

- **Path Parsing**: Fixed issue with relative paths like `calculator/calculator.py`
- **Cross-Repo Detection**: Smart detection that doesn't trigger on same-repo paths
- **File Access**: Proper file existence checking and content fetching
- **Target Processing**: Handles `Target: RepoName/file.py` correctly

## Setup Complete! ✅

Your TicketWatcher is now installed with all the latest fixes. Next steps:

1. **Enable GitHub Actions:**
   - Go to your repository Settings
   - Click "Actions" → "General"
   - Under "Workflow permissions", select "Read and write permissions"
   - Check "Allow GitHub Actions to create and approve pull requests"

2. **Add your OpenAI API key:**
   - Go to Settings → Secrets and variables → Actions
   - Click "New repository secret"
   - Name: `OPENAI_API_KEY`
   - Value: Your OpenAI API key from https://platform.openai.com/api-keys

3. **Test it:**
   - Create an issue with label `agent-fix`
   - Include a target like: `Target: calculator/calculator.py`
   - Or include a traceback in the issue body
   - Watch the magic happen! ✨

## Supported Target Formats

The agent now properly handles:

- `Target: calculator/calculator.py` ✅
- `Target: TestIssueRepo/calculator/calculator.py` ✅ (same repo)
- `Target: src/app/auth.py` ✅
- `Target: ./calculator/calculator.py` ✅

## Optional Configuration

You can customize the behavior by adding these secrets to your repository:

**Required:**
- `OPENAI_API_KEY` - Your OpenAI API key

**Optional (with defaults):**
- `TICKETWATCHER_TRIGGER_LABELS` - Labels that trigger the agent (default: agent-fix,auto-pr)
- `ALLOWED_PATHS` - Paths the agent can modify (default: src/,app/,calculator/)
- `MAX_FILES` - Max files to modify per fix (default: 4)
- `MAX_LINES` - Max lines to change per fix (default: 200)
- `DEFAULT_AROUND_LINES` - Lines of context around errors (default: 60)
- `TICKETWATCHER_BASE_BRANCH` - Base branch for PRs (default: main)
- `TICKETWATCHER_BRANCH_PREFIX` - Branch name prefix (default: agent-fix/)
- `TICKETWATCHER_MODEL` - AI model (default: gpt-4o-mini)

To customize behavior, add these as **GitHub repository secrets** (Settings → Secrets and variables → Actions).

## How it works

1. When an issue is created/updated with the right label
2. The agent analyzes the issue and code
3. Creates a draft PR with the fix
4. Comments on the issue with the PR link

## Source

This version uses the VickramC07 fork with all fixes: https://github.com/VickramC07/GITHUB-MCP-TICKET-AGENT-LIBRARY
EOF

# Create a simple test script
cat > test-ticketer.sh << 'EOF'
#!/bin/bash
echo "🧪 Testing TicketWatcher installation (Fixed Version)..."

# Check if we're in a git repo
if [ ! -d ".git" ]; then
    echo "❌ Not in a git repository. Please run this from your git repo root."
    exit 1
fi

# Check if ticketer directory exists
if [ ! -d "ticketer" ]; then
    echo "❌ ticketer directory not found. Please run the install script first."
    exit 1
fi

# Check if workflow file exists
if [ ! -f ".github/workflows/ticket-agent.yml" ]; then
    echo "❌ GitHub Actions workflow not found."
    exit 1
fi

echo "✅ Installation looks good!"
echo ""
echo "Next steps:"
echo "1. Commit and push the ticketer folder:"
echo "   git add ticketer/ .github/"
echo "   git commit -m 'Add TicketWatcher (Fixed Version)'"
echo "   git push"
echo ""
echo "2. Enable GitHub Actions in your repository settings"
echo "3. Add OPENAI_API_KEY to your repository secrets"
echo "4. Create a test issue with label 'agent-fix' and target 'Target: calculator/calculator.py'"
EOF

chmod +x test-ticketer.sh

echo "✅ TicketWatcher installation complete! (Fixed Version)"
echo ""
echo "📁 Created:"
echo "   - ticketer/ directory with source code (with all fixes)"
echo "   - .github/workflows/ticket-agent.yml"
echo ""
echo "🔧 What's Fixed:"
echo "   - Path parsing for relative paths like calculator/calculator.py"
echo "   - Smart cross-repo detection (won't trigger on same repo)"
echo "   - Proper file access and content fetching"
echo "   - Support for Target: RepoName/file.py format"
echo ""
echo "Next steps:"
echo "1. Commit and push the changes:"
echo "   git add ticketer/ .github/"
echo "   git commit -m 'Add TicketWatcher (Fixed Version)'"
echo "   git push"
echo ""
echo "2. Enable GitHub Actions:"
echo "   - Go to Settings → Actions → General"
echo "   - Enable 'Read and write permissions'"
echo ""
echo "3. Add your OpenAI API key:"
echo "   - Go to Settings → Secrets and variables → Actions"
echo "   - Add OPENAI_API_KEY secret"
echo ""
echo "4. Test it:"
echo "   - Create an issue with label 'agent-fix'"
echo "   - Use target: 'Target: calculator/calculator.py'"
echo "   - Or include a traceback in the issue body"
echo ""
echo "🎉 You're all set! The agent will now work correctly with your file paths."
echo "📦 Using source: https://github.com/VickramC07/GITHUB-MCP-TICKET-AGENT-LIBRARY (with fixes)"
