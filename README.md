# 🤖 GitHub MCP Ticket Agent Library

> **An intelligent GitHub issue automation system that uses AI to analyze bug reports and automatically create fix proposals via pull requests.**

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![GitHub Actions](https://img.shields.io/badge/GitHub%20Actions-ready-green.svg)](https://github.com/features/actions)
[![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4-orange.svg)](https://openai.com/)

## 🚀 What is TicketWatcher?

TicketWatcher is an intelligent automation library that transforms GitHub issues into actionable pull requests. When you create an issue with a bug report or traceback, the AI agent analyzes the code, understands the problem, and automatically creates a draft PR with a proposed fix.

### ✨ Key Features

- **🎯 Smart Issue Analysis**: Parses tracebacks and error messages to identify problematic files
- **🧠 AI-Powered Fixes**: Uses OpenAI's GPT models to generate intelligent code patches
- **🔒 Safe & Constrained**: Operates within configurable file path restrictions and change limits
- **📝 Draft PR Creation**: Automatically creates draft pull requests for human review
- **🔄 Iterative Context**: Can request additional code context when needed
- **⚡ GitHub Actions Ready**: Seamlessly integrates with GitHub workflows
- **🛡️ Path Validation**: Ensures only allowed files are modified

## 🏗️ How It Works

```mermaid
graph TD
    A[GitHub Issue Created] --> B{Contains Trigger Label?}
    B -->|No| C[No Action]
    B -->|Yes| D[Parse Issue Content]
    D --> E[Extract File Paths & Line Numbers]
    E --> F[Fetch Code Snippets]
    F --> G[Send to AI Agent]
    G --> H{Need More Context?}
    H -->|Yes| I[Request Additional Files]
    I --> G
    H -->|No| J[Generate Unified Diff]
    J --> K{Within Limits?}
    K -->|No| L[Comment on Issue]
    K -->|Yes| M[Create Branch]
    M --> N[Apply Changes]
    N --> O[Create Draft PR]
    O --> P[Comment with PR Link]
```

## 🛠️ Technologies Used

### Core Technologies
- **Python 3.9+**: Modern Python with type hints and async support
- **OpenAI API**: GPT-4/GPT-4o-mini for intelligent code analysis and fix generation
- **GitHub API v4**: Full repository manipulation capabilities
- **Requests**: HTTP client for API interactions

### Architecture Components
- **🎭 Agent LLM Module**: Intelligent AI agent with structured JSON responses
- **🔌 GitHub API Wrapper**: Comprehensive GitHub repository operations
- **📋 Event Handlers**: Issue and comment event processing
- **🖥️ CLI Interface**: Command-line interface for GitHub Actions integration
- **🧪 Test Suite**: Comprehensive testing including live integration tests

## 🚀 Quick Start

### 1. Fork This Repository
Click the "Fork" button to create your own copy of this repository.

### 2. Add GitHub Secrets
In your fork's repository settings, go to **Settings > Secrets and variables > Actions** and add these secrets:

- **`OPENAI_API_KEY`**: Your OpenAI API key

> **Note**: The `GITHUB_TOKEN` is automatically provided by GitHub Actions, so you don't need to add it manually.

### 3. Enable GitHub Actions
The workflow is already configured and will run automatically when:

- Issues are opened with `[agent-fix]` or `[auto-pr]` labels
- Comments contain `/agent fix`

### 4. Optional Configuration
You can customize the behavior by adding these environment variables in your repository settings:

| Variable | Default | Description |
|----------|---------|-------------|
| `TICKETWATCHER_TRIGGER_LABELS` | `agent-fix,auto-pr` | Labels that trigger the agent |
| `ALLOWED_PATHS` | `src/,app/` | Paths the agent can modify |
| `MAX_FILES` | `4` | Maximum files to modify |
| `MAX_LINES` | `200` | Maximum lines to change |

**That's it!** 🎉 The system is now ready to use with GitHub Actions!

## 📖 Usage Guide

### Creating Issues That Trigger the Agent

The agent responds to issues with specific labels or patterns:

#### Method 1: Use Trigger Labels
Create an issue with labels like `agent-fix` or `auto-pr`:

```markdown
## Bug Report

**Error:**
```
Traceback (most recent call last):
  File "src/app/auth.py", line 42, in get_user_profile
    return user["name"]
KeyError: 'name'
```

**Expected Behavior:**
The function should handle cases where the user object doesn't have a 'name' key.
```

#### Method 2: Comment Trigger
Comment on any issue with `/agent fix` to trigger the agent:

```
/agent fix

Please analyze this authentication issue and propose a fix.
```

### How It Works

When you create an issue with a trigger label, the AI will:

1. **🔍 Analyze** the issue for context clues
2. **📁 Detect** relevant files automatically  
3. **❓ Request** specific information if needed
4. **📝 Create** a draft PR with the fix
5. **💭 Show** thinking process in comments

### Example Interaction

**Issue Created:**
```
Title: [agent-fix] Authentication bug in user profile
Body: I'm getting a crash when trying to get user profiles. 
The error happens when user data is missing some fields.
```

**AI Response:**
```
🤖 TicketWatcher Analysis

AI Thinking Process:
I can see this is an authentication issue. The user mentions "user profiles" 
and "crash", which suggests the problem is likely in the user authentication 
system. I should examine the auth.py file.

Issue: I need to see the authentication code to understand the crash

To help me fix this issue, please provide:
1. A traceback: File "src/app/auth.py", line 10
2. Or a target hint: Target: src/app/auth.py  
3. Or just mention the file: "auth.py" and I'll find it!

I'm ready to help once I have the right context! 🚀
```

### Understanding the Agent's Process

1. **📊 Issue Analysis**: The agent parses your issue content for:
   - File paths from tracebacks: `File "src/app/auth.py", line 42`
   - Target hints: `Target: src/app/utils.py`
   - Error messages and context

2. **🔍 Code Fetching**: Retrieves relevant code snippets around the problematic areas

3. **🤖 AI Analysis**: Uses GPT to understand the issue and propose a fix

4. **📝 Patch Generation**: Creates a unified diff with minimal, safe changes

5. **🔄 PR Creation**: Automatically creates a draft PR with the proposed fix

## ⚙️ Configuration Options

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `TICKETWATCHER_TRIGGER_LABELS` | `agent-fix,auto-pr` | Comma-separated labels that trigger the agent |
| `ALLOWED_PATHS` | `src/,app/` | Paths the agent is allowed to modify |
| `MAX_FILES` | `4` | Maximum files to modify per fix |
| `MAX_LINES` | `200` | Maximum lines to change per fix |
| `DEFAULT_AROUND_LINES` | `60` | Lines of context to fetch around error locations |
| `TICKETWATCHER_BASE_BRANCH` | `main` | Base branch for PR creation |
| `TICKETWATCHER_BRANCH_PREFIX` | `agent-fix/` | Prefix for generated branch names |
| `OPENAI_API_KEY` | *required* | Your OpenAI API key |
| `GITHUB_TOKEN` | *required* | GitHub Personal Access Token |

### Advanced Configuration

```python
# Custom agent configuration
agent = TicketWatcherAgent(
    model="gpt-4o-mini",  # or "gpt-4"
    allowed_paths=["src/", "app/", "lib/"],
    max_files=6,
    max_total_lines=300,
    default_around_lines=80
)
```

## 🧪 Testing

### Run Unit Tests
```bash
python -m pytest test/ -v
```

### Live Integration Test
```bash
# Set up environment variables first
export GITHUB_TOKEN=your_token
export GITHUB_REPOSITORY=owner/repo
export OPENAI_API_KEY=your_key

# Run live test (creates real issue and PR)
python test/live_integration_test.py
```

### Manual Testing
```bash
# Test with a sample event file
python scripts/live_test.py
```

## 🔒 Security & Safety

### Built-in Safety Features

- **Path Restrictions**: Only modifies files in allowed directories
- **Change Limits**: Configurable limits on files and lines changed
- **Draft PRs**: All generated PRs are created as drafts for review
- **Validation**: Comprehensive validation of proposed changes
- **Error Handling**: Graceful handling of API failures and edge cases

### Best Practices

1. **Review All Draft PRs**: Always review agent-generated changes before merging
2. **Use Restricted Paths**: Limit `ALLOWED_PATHS` to essential directories
3. **Monitor Usage**: Keep track of API usage and costs
4. **Test Thoroughly**: Use the test suite to validate behavior
5. **Backup Important Code**: Ensure you have backups before automation

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guidelines](CONTRIBUTING.md) for details.

### Development Setup

```bash
# Clone and setup
git clone https://github.com/your-username/github-mcp-ticket-agent-library.git
cd github-mcp-ticket-agent-library

# Install in development mode
pip install -e ".[dev]"

# Run tests
pytest test/ -v

# Run linting
flake8 src/
```

## 📚 API Reference

### TicketWatcherAgent

The core AI agent class that handles issue analysis and fix generation.

```python
from ticketwatcher.agent_llm import TicketWatcherAgent

agent = TicketWatcherAgent(
    model="gpt-4o-mini",
    allowed_paths=["src/"],
    max_files=4,
    max_total_lines=200
)

result = agent.run(
    ticket_title="Bug in authentication",
    ticket_body="Error occurs when...",
    snippets=[{"path": "src/auth.py", "start_line": 1, "end_line": 50, "code": "..."}]
)
```

### GitHub API Functions

```python
from ticketwatcher.github_api import (
    create_branch,
    create_or_update_file,
    create_pr,
    get_file_text
)

# Create a new branch
create_branch("feature/fix-auth", base="main")

# Update a file
create_or_update_file(
    path="src/auth.py",
    content_text="def fixed_function(): ...",
    message="Fix authentication bug",
    branch="feature/fix-auth"
)

# Create a pull request
pr_url, pr_number = create_pr(
    title="Fix authentication bug",
    head="feature/fix-auth",
    base="main",
    body="Automated fix for issue #123"
)
```

## 🐛 Troubleshooting

### Common Issues

**Agent doesn't trigger:**
- Check that your issue has the correct trigger labels
- Verify the GitHub Actions workflow is running
- Ensure environment variables are set correctly

**"Path not allowed" errors:**
- Update `ALLOWED_PATHS` environment variable
- Ensure file paths in issues match allowed patterns

**API rate limits:**
- Check your OpenAI API usage
- Verify GitHub token permissions
- Consider implementing rate limiting

**Generated fixes are incorrect:**
- Provide more context in the issue description
- Include relevant code snippets
- Use more specific error messages

### Getting Help

- 📖 Check the [documentation](docs/)
- 🐛 Report issues on [GitHub Issues](https://github.com/your-username/github-mcp-ticket-agent-library/issues)
- 💬 Join our [Discussions](https://github.com/your-username/github-mcp-ticket-agent-library/discussions)

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- OpenAI for providing the GPT models that power the intelligent analysis
- GitHub for the comprehensive API and Actions platform
- The Python community for excellent libraries and tools

---

**Ready to automate your bug fixing workflow?** 🚀

Start by setting up the GitHub Action and creating your first issue with the `agent-fix` label. The agent will analyze your bug report and create a draft PR with a proposed fix - all automatically!

> 💡 **Pro Tip**: Start with small, well-defined bugs to see how the agent works, then gradually expand to more complex issues as you gain confidence in the system.