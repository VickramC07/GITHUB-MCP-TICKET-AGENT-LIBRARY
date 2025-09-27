# TicketWatcher

An intelligent AI-powered GitHub issue handler that automatically analyzes issues and creates pull requests with fixes.

## Features

- **Smart Context Detection**: Automatically detects relevant files from issue descriptions
- **AI Thinking Process**: Shows reasoning in comments and PRs
- **Progressive Information Gathering**: Asks for specific context when needed
- **GitHub Actions Integration**: Runs automatically on issue events

## Setup

### 1. Fork this repository

### 2. Add GitHub Secrets
In your fork's settings, add these secrets:
- `OPENAI_API_KEY`: Your OpenAI API key

### 3. Enable GitHub Actions
The workflow will run automatically when:
- Issues are opened with `[agent-fix]` or `[auto-pr]` labels
- Comments contain `/agent fix`

## How It Works

1. **Issue Created**: User creates issue with trigger label
2. **AI Analysis**: System analyzes issue and detects context
3. **Smart Response**: Either requests more context or creates PR
4. **Transparent Process**: Shows AI thinking in comments

## Configuration

Set these environment variables in your repository settings:

- `TICKETWATCHER_TRIGGER_LABELS`: Labels that trigger the agent (default: `agent-fix,auto-pr`)
- `ALLOWED_PATHS`: Paths the agent can modify (default: `src/,app/`)
- `MAX_FILES`: Maximum files to modify (default: `4`)
- `MAX_LINES`: Maximum lines to change (default: `200`)

## Usage

Create an issue with a trigger label and the AI will:

1. **Analyze the issue** for context clues
2. **Detect relevant files** automatically
3. **Request specific information** if needed
4. **Create a draft PR** with the fix
5. **Show thinking process** in comments

## Example

**Issue:**
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

The system is now ready to use with GitHub Actions!