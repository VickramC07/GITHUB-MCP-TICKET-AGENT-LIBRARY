from __future__ import annotations
import os
import re
import json
from typing import List, Tuple, Iterable, Dict, Any, Optional

from .github_api import (
    get_default_branch,
    create_branch,
    create_or_update_file,
    create_pr,
    get_file_text,
    file_exists,              # add this small helper in github_api if you don’t have it yet
    add_issue_comment,         # optional but nice to have
)

from .agent_llm import TicketWatcherAgent  # the class we just finished


# --------- config knobs (can be env driven) ---------
TRIGGER_LABELS = set(os.getenv("TICKETWATCHER_TRIGGER_LABELS", "agent-fix,auto-pr").split(","))
BRANCH_PREFIX  = os.getenv("TICKETWATCHER_BRANCH_PREFIX", "agent-fix/")
PR_TITLE_PREF  = os.getenv("TICKETWATCHER_PR_TITLE_PREFIX", "agent: auto-fix for issue")
ALLOWED_PATHS  = [p.strip() for p in os.getenv("ALLOWED_PATHS", "src/,app/").split(",") if p.strip()]
MAX_FILES      = int(os.getenv("MAX_FILES", "4"))
MAX_LINES      = int(os.getenv("MAX_LINES", "200"))
AROUND_LINES   = int(os.getenv("DEFAULT_AROUND_LINES", "60"))
REPO_ROOT = os.getenv("GITHUB_WORKSPACE")
REPO_NAME = (os.getenv("GITHUB_REPOSITORY") or "").split("/", 1)[-1] or os.path.basename(REPO_ROOT)

# ----------------------------------------------------


def _mk_branch(issue_number: int) -> str:
    return f"{BRANCH_PREFIX}{issue_number}"


# ---------- seed parsing & snippet fetch ----------

REPO_ROOT = os.getenv("GITHUB_WORKSPACE") or os.getcwd()
REPO_NAME = (os.getenv("GITHUB_REPOSITORY") or "").split("/", 1)[-1] or os.path.basename(REPO_ROOT)

_RE_PY_FILELINE = re.compile(r'File\s+"([^"]+)"\s*,\s*line\s+(\d+)\b')
_RE_GENERIC_PATHLINE = re.compile(r'([^\s\'",)\]]+):(\d+)\b')  # token:line
_RE_TARGET = re.compile(r'^\s*Target:\s*(.+?)\s*$', re.MULTILINE)  # Target: path[ :line]

def _sanitize_path_token(tok: str) -> str:
    """Strip wrapping quotes/backticks and trailing punctuation."""
    tok = (tok or "").strip()
    tok = tok.strip('`"\'')

    # drop trailing punctuation/junk that commonly follows paths in traces
    tok = re.sub(r'[\'"\s,)\]>]+$', '', tok)
    return tok

def _to_repo_relative(path: str) -> str:
    """Return a path relative to the repo root (e.g., 'src/app/auth.py')."""
    p = (path or "").strip().replace("\\", "/")
    print(f"🔍 DEBUG: Converting path '{path}' to repo-relative")

    # If it includes '<repo_name>/', trim up to that
    needle = f"/{REPO_NAME}/"
    if needle in p:
        p = p.split(needle, 1)[1]
        print(f"   Trimmed repo name: '{p}'")

    # Handle absolute paths from tracebacks
    if os.path.isabs(p):
        print(f"   Absolute path detected: '{p}'")
        # Try to find the repo root in the path
        if REPO_ROOT in p:
            # Extract the part after the repo root
            try:
                rel = os.path.relpath(p, REPO_ROOT).replace("\\", "/")
                result = rel.lstrip("./").lstrip("/")
                print(f"   Extracted from repo root: '{result}'")
                return result
            except Exception as e:
                print(f"   Error extracting from repo root: {e}")
        
        # Try to find common patterns in absolute paths
        # Look for any directory that might be a project directory
        path_parts = p.split("/")
        for i, part in enumerate(path_parts):
            if part and i < len(path_parts) - 1:  # Not the last part
                # Check if this looks like a project directory
                if part not in ["Users", "home", "tmp", "var", "opt", "usr", "bin", "sbin", "etc"]:
                    # Extract everything from this directory onwards
                    result = "/".join(path_parts[i:])
                    print(f"   Extracted project path: '{result}'")
                    return result
        
        # Try to find src/... part
        if "/src/" in p:
            parts = p.split("/src/")
            if len(parts) > 1:
                result = f"src/{parts[1]}"
                print(f"   Extracted src path: '{result}'")
                return result

    # If it's already a simple relative path (no leading slash, no absolute path components),
    # keep it as-is to avoid converting to absolute paths
    if not p.startswith("/") and not p.startswith(REPO_ROOT) and not os.path.isabs(p):
        result = p.lstrip("./").lstrip("/")
        print(f"   Simple relative path: '{result}'")
        return result

    # If absolute and under the workspace, relativize
    try:
        rel = os.path.relpath(p, REPO_ROOT).replace("\\", "/")
        result = rel.lstrip("./").lstrip("/")
        print(f"   Relativized path: '{result}'")
        return result
    except Exception as e:
        print(f"   Error relativizing: {e}, using original: '{p}'")
        return p.lstrip("./").lstrip("/")

def _path_allowed_with(path: str, allowed_prefixes: Iterable[str] | None) -> bool:
    """Allowlist check; if prefixes empty/None or contains '', allow all."""
    if not allowed_prefixes or any(a == "" for a in allowed_prefixes):
        return True
    p = _to_repo_relative(path)  # ensure repo-relative
    for a in allowed_prefixes:
        if not a:
            return True
        a = a if a.endswith("/") else a + "/"
        if p == a[:-1] or p.startswith(a):
            return True
    return False

def _path_allowed(path: str) -> bool:
    """Single-arg convenience using the global ALLOWED_PATHS."""
    return _path_allowed_with(path, ALLOWED_PATHS)

def parse_stack_text(
    text: str,
    *,
    allowed_prefixes: Iterable[str] | None = None,
    limit: int = 5,
) -> List[Tuple[str, int | None]]:
    """
    Extract (repo-relative path, line|None) pairs from mixed stack/trace text.
    Order-preserving, de-duplicated, capped by 'limit'.
    """
    out: List[Tuple[str, int | None]] = []

    if not text:
        return out
    #print(f'text{text}')
    lines = text.splitlines()

    # 1) Python "File "...", line N"
    for line in lines:
        #print(f'line:{line}')
        m = _RE_PY_FILELINE.search(line)
        if not m:
            continue
        raw = _sanitize_path_token(m.group(1))
        path = _to_repo_relative(raw)
        line_no = int(m.group(2))
        if path and _path_allowed(path):
            out.append((path, line_no))
    #print(f'out1{out}')
    # 2) Generic "token:LINE"
    for line in lines:
        for m in _RE_GENERIC_PATHLINE.finditer(line):
            raw = _sanitize_path_token(m.group(1))
            path = _to_repo_relative(raw)
            line_no = int(m.group(2))
            if path and _path_allowed(path):
                out.append((path, line_no))

    # 3) "Target: path" (optional ":line" allowed)
    for m in _RE_TARGET.finditer(text):
        raw_full = _sanitize_path_token(m.group(1))
        # if someone wrote "Target: path:123", capture the line too
        if ":" in raw_full and raw_full.rsplit(":", 1)[-1].isdigit():
            raw_path, raw_line = raw_full.rsplit(":", 1)
            line_no = int(raw_line)
        else:
            raw_path, line_no = raw_full, None
        path = _to_repo_relative(raw_path)
        if path and _path_allowed(path):
            out.append((path, line_no))

    # 4) De-dupe while preserving order, then cap
    seen: set[Tuple[str, int]] = set()
    uniq: List[Tuple[str, int | None]] = []

    for p, ln in out:
        key = (p, ln or 0)
        if key in seen:
            continue
        seen.add(key)
        uniq.append((p, ln))
        #print(f'uniq{uniq}')
        if len(uniq) >= max(1, limit):
            break

    return uniq


def _fetch_slice(path: str, base: str, center_line: int | None, around: int) -> Dict[str, Any] | None:
    """Fetch ±around lines for a file (centered at center_line if given)."""
    print(f"🔍 Attempting to fetch slice for path: '{path}'")
    print(f"   Path allowed: {_path_allowed(path)}")
    print(f"   File exists: {file_exists(path, base)}")
    
    if not _path_allowed(path):
        print(f"❌ Path '{path}' not allowed. Allowed paths: {ALLOWED_PATHS}")
        return None
    if not file_exists(path, base):
        print(f"❌ File '{path}' does not exist on branch '{base}'")
        return None
        
    content = get_file_text(path, base)
    lines = content.splitlines()
    n = len(lines)
    if center_line is None or center_line < 1 or center_line > n:
        # whole file is too big; return head slice
        start = 1
        end = min(n, 2 * around)
    else:
        start = max(1, center_line - around)
        end = min(n, center_line + around)
    code = "\n".join(lines[start - 1 : end])
    print(f"✅ Successfully fetched {len(code)} characters from '{path}'")
    return {"path": path, "start_line": start, "end_line": end, "code": code}


def _fetch_symbol_slice(path: str, base: str, symbol: str, around: int) -> Dict[str, Any] | None:
    """Naive symbol search to find a 'def <symbol>' or occurrence and slice around it."""
    if not _path_allowed(path)or not file_exists(path, base):
        return None
    content = get_file_text(path, base)
    lines = content.splitlines()
    # Look for a definition first
    def_pat = re.compile(rf'^\s*(def|class)\s+{re.escape(symbol)}\b')
    idx = None
    for i, line in enumerate(lines, start=1):
        if def_pat.search(line):
            idx = i
            break
    if idx is None:
        # fallback: first occurrence
        for i, line in enumerate(lines, start=1):
            if symbol in line:
                idx = i
                break
    if idx is None:
        return None
    start = max(1, idx - around)
    end = min(len(lines), idx + around)
    code = "\n".join(lines[start - 1 : end])
    return {"path": path, "start_line": start, "end_line": end, "code": code}


# ---------- unified diff parsing / application ----------

_HUNK_RE = re.compile(r'^@@ -(\d+),?(\d+)? \+(\d+),?(\d+)? @@')

def _parse_unified_diff(diff_text: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    Parse a unified diff into a dict: { path: [ {old_start, old_len, new_start, new_len, lines: [...]}, ... ] }
    Supports multi-file diffs for typical small patches.
    """
    files: Dict[str, List[Dict[str, Any]]] = {}
    cur_file = None
    cur_hunk = None
    lines = diff_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith('--- a/'):
            # next line should be +++ b/<path>
            if i + 1 < len(lines) and lines[i + 1].startswith('+++ b/'):
                path = lines[i + 1][6:]
                cur_file = path
                files.setdefault(cur_file, [])
                i += 2
                continue
        m = _HUNK_RE.match(line)
        if m and cur_file:
            old_start = int(m.group(1))
            old_len   = int(m.group(2) or "1")
            new_start = int(m.group(3))
            new_len   = int(m.group(4) or "1")
            cur_hunk = {"old_start": old_start, "old_len": old_len, "new_start": new_start, "new_len": new_len, "lines": []}
            files[cur_file].append(cur_hunk)
            i += 1
            # collect hunk lines until next header/file
            while i < len(lines) and not lines[i].startswith('@@') and not lines[i].startswith('--- a/'):
                cur_hunk["lines"].append(lines[i])
                i += 1
            continue
        i += 1
    return files


def _apply_hunks_to_text(orig_text: str, hunks: List[Dict[str, Any]]) -> str:
    """
    Very small, forgiving hunk applier for typical patches produced by the agent.
    Assumes hunks are in ascending order and apply cleanly.
    """
    src = orig_text.splitlines()
    dst = []
    cursor = 1  # 1-based
    
    for h in hunks:
        old_start = h["old_start"]
        old_len = h["old_len"]
        
        # copy unchanged lines up to the hunk
        while cursor < old_start:
            dst.append(src[cursor - 1])
            cursor += 1
        
        # Process the hunk lines
        hunk_lines = h["lines"]
        src_cursor = cursor
        
        for ln in hunk_lines:
            if ln.startswith(' '):
                # context line: must match src, copy from both
                if src_cursor <= len(src):
                    dst.append(src[src_cursor - 1])
                src_cursor += 1
            elif ln.startswith('-'):
                # deletion: skip in src, don't add to dst
                src_cursor += 1
            elif ln.startswith('+'):
                # addition: add to dst, don't advance src
                dst.append(ln[1:])
            else:
                # unknown marker, treat as context
                if src_cursor <= len(src):
                    dst.append(src[src_cursor - 1])
                src_cursor += 1
        
        # Update cursor to end of processed hunk
        cursor = src_cursor
    
    # copy the rest
    while cursor <= len(src):
        dst.append(src[cursor - 1])
        cursor += 1
    
    return "\n".join(dst)


def _apply_unified_diff(base_ref: str, diff_text: str) -> Dict[str, str]:
    """
    Fetch current file contents from base_ref, apply hunks, return {path: updated_text}.
    Rejects paths outside ALLOWED_PATHS.
    """
    parsed = _parse_unified_diff(diff_text)
    updated: Dict[str, str] = {}
    for path, hunks in parsed.items():
        if not _path_allowed(path):
            raise ValueError(f"Path not allowed: {path}")
        # if not file_exists(path, base_ref):
        #     raise ValueError(f"File does not exist on base: {path}")
        current = get_file_text(path, base_ref)
        new_text = _apply_hunks_to_text(current, hunks)
        updated[path] = new_text
    return updated


def _diff_stats(diff_text: str) -> Tuple[int, int]:
    """Return (files_touched, changed_lines)."""
    files = set()
    changes = 0
    for ln in diff_text.splitlines():
        if ln.startswith('--- a/'):
            pass
        elif ln.startswith('+++ b/'):
            files.add(ln[6:])
        elif ln.startswith('+') and not ln.startswith('+++'):
            changes += 1
        elif ln.startswith('-') and not ln.startswith('---'):
            changes += 1
    return (len(files), changes)


# ---------- main handlers ----------

def handle_issue_event(event: Dict[str, Any]) -> Optional[str]:
    action = event.get("action")
    issue  = event.get("issue") or {}
    number = issue.get("number")
    labels = {l["name"] for l in issue.get("labels", [])}

    # Trigger only for relevant events/labels
    if not (action in {"opened", "reopened"} or action == "labeled" or (labels & TRIGGER_LABELS)):
        return None
    if action == "labeled":
        lab = (event.get("label") or {}).get("name")
        if lab and lab not in TRIGGER_LABELS:
            return None

    title = issue.get("title", "")
    body  = issue.get("body", "") or ""
    base  = os.getenv("TICKETWATCHER_BASE_BRANCH") or get_default_branch()
    
    # DEBUG: Show environment and configuration
    print(f"🔍 DEBUG: TicketWatcher Analysis Starting")
    print(f"   Working Directory: {os.getcwd()}")
    print(f"   Repository Root: {REPO_ROOT}")
    print(f"   Repository Name: {REPO_NAME}")
    print(f"   Base Branch: {base}")
    print(f"   Allowed Paths: {ALLOWED_PATHS}")
    print(f"   Max Files: {MAX_FILES}")
    print(f"   Max Lines: {MAX_LINES}")
    print(f"   Issue Title: {title}")
    print(f"   Issue Body: {body[:200]}...")
    
    # DEBUG: Show directory structure
    print(f"📁 Directory Structure:")
    try:
        for root, dirs, files in os.walk("."):
            level = root.replace(".", "").count(os.sep)
            indent = " " * 2 * level
            print(f"{indent}{os.path.basename(root)}/")
            subindent = " " * 2 * (level + 1)
            for file in files[:5]:  # Show first 5 files
                print(f"{subindent}{file}")
            if len(files) > 5:
                print(f"{subindent}... and {len(files) - 5} more files")
    except Exception as e:
        print(f"   Could not scan directory structure: {e}")
    
    # Check for cross-repository references (only for actual different repos)
    cross_repo_patterns = [
        r'Target:\s*([^/\s]+/[^/\s]+):([^\s]+)',  # owner/repo:path
        r'https://github\.com/([^/\s]+/[^/\s]+)/blob/[^/]+/(.+)',  # GitHub URL
    ]
    
    # Get current repository info
    current_repo = os.getenv("GITHUB_REPOSITORY", "")
    current_repo_name = current_repo.split("/", 1)[-1] if "/" in current_repo else current_repo
    
    for pattern in cross_repo_patterns:
        match = re.search(pattern, body)
        if match:
            if len(match.groups()) == 2:
                repo_part = match.group(1)
                path_part = match.group(2)
                
                # Only treat as cross-repo if it's actually a different repository
                if repo_part != current_repo and repo_part != current_repo_name:
                    # Create helpful comment for cross-repo issue
                    comment = f"""🤖 **TicketWatcher Analysis**

**Cross-Repository Issue Detected**

I detected a reference to a different repository: `{repo_part}`

**Current Limitation:** TicketWatcher can only fix issues within the same repository where it's installed.

**Solutions:**
1. **Move the issue** to the `{repo_part}` repository
2. **Install TicketWatcher** in the `{repo_part}` repository  
3. **Copy the relevant code** to this repository for analysis

**Target file:** `{path_part}` in `{repo_part}`

**To install TicketWatcher in the target repository:**
```bash
# In the {repo_part} repository:
# 1. Copy the workflow file
# 2. Copy the src/ticketwatcher/ directory
# 3. Add requirements.txt
# 4. Set up GitHub secrets (OPENAI_API_KEY)
```

Would you like me to help you with any of these options? 🚀"""
                    
                    add_issue_comment(number, comment)
                    return None
    
    # Handle cases like "Target: RepoName/file.py" 
    # where RepoName might be the current repo name
    repo_name_pattern = r'Target:\s*([^/\s]+)/([^\s]+)'
    repo_match = re.search(repo_name_pattern, body)
    if repo_match:
        repo_name = repo_match.group(1)
        file_path = repo_match.group(2)
        
        # If the repo name matches the current repo name, treat it as a local path
        if repo_name == current_repo_name:
            # Replace the target with just the file path for normal processing
            body = body.replace(f"Target: {repo_name}/{file_path}", f"Target: {file_path}")
            print(f"🔄 Converted {repo_name}/{file_path} to {file_path} (same repository)")
        elif repo_name != current_repo and repo_name != current_repo_name:
            # It's actually a different repository
            comment = f"""🤖 **TicketWatcher Analysis**

**Cross-Repository Issue Detected**

I detected a reference to a different repository: `{repo_name}`

**Current Limitation:** TicketWatcher can only fix issues within the same repository where it's installed.

**Solutions:**
1. **Move the issue** to the `{repo_name}` repository
2. **Install TicketWatcher** in the `{repo_name}` repository  
3. **Copy the relevant code** to this repository for analysis

**Target file:** `{file_path}` in `{repo_name}`

**To install TicketWatcher in the target repository:**
```bash
# In the {repo_name} repository:
# 1. Copy the workflow file
# 2. Copy the src/ticketwatcher/ directory
# 3. Add requirements.txt
# 4. Set up GitHub secrets (OPENAI_API_KEY)
```

Would you like me to help you with any of these options? 🚀"""
            
            add_issue_comment(number, comment)
            return None

    # 1) Enhanced file detection - try multiple approaches
    print(f"🤖 Enhanced file detection starting...")
    
    # Create agent instance first
    agent = TicketWatcherAgent(
        allowed_paths=ALLOWED_PATHS,
        max_files=MAX_FILES,
        max_total_lines=MAX_LINES,
        default_around_lines=AROUND_LINES,
    )
    
    # First, try to detect files from the issue content
    detected_files = []
    
    # Check for explicit file references and traceback paths
    explicit_files = []
    
    # 1. Check for explicit Target: lines
    for line in body.split('\n'):
        if 'Target:' in line:
            target_match = re.search(r'Target:\s*(.+)', line)
            if target_match:
                file_path = target_match.group(1).strip().strip('"\'')
                explicit_files.append(file_path)
                print(f"🎯 Found explicit target: {file_path}")
    
    # 2. Check for Python traceback file paths
    traceback_patterns = [
        r'File\s+"([^"]+)"\s*,\s*line\s+\d+',  # File "path", line N
        r'File\s+([^\s,]+)\s*,\s*line\s+\d+',   # File path, line N
    ]
    
    for pattern in traceback_patterns:
        matches = re.findall(pattern, body)
        for match in matches:
            # Convert absolute paths to relative paths
            file_path = _to_repo_relative(match)
            if file_path and _path_allowed(file_path):
                if file_path not in explicit_files:  # Avoid duplicates
                    explicit_files.append(file_path)
                    print(f"🎯 Found traceback file: {file_path}")
    
    print(f"📁 Total explicit files found: {explicit_files}")
    
    # Add explicit files first
    detected_files.extend(explicit_files)
    
    # Only search for general files if no explicit targets were found
    if not explicit_files:
        print(f"🔍 No explicit targets found, searching for Python files in allowed directories...")
        for allowed_dir in ALLOWED_PATHS:
            # Look for common Python file patterns in each allowed directory
            potential_files = [
                f"{allowed_dir}main.py",
                f"{allowed_dir}app.py", 
                f"{allowed_dir}index.py",
                f"{allowed_dir}src/main.py",
                f"{allowed_dir}src/app.py",
                f"{allowed_dir}lib/main.py",
                f"{allowed_dir}lib/app.py"
            ]
            for file_path in potential_files:
                if _path_allowed(file_path):
                    detected_files.append(file_path)
                    print(f"🎯 Added potential file: {file_path}")
                    break  # Only add one file per directory to avoid too many files
    else:
        # If we found explicit files but they don't exist, try to find similar files
        print(f"🔍 Explicit files found but checking if they exist...")
        existing_files = []
        for file_path in explicit_files:
            if file_exists(file_path, base):
                existing_files.append(file_path)
                print(f"✅ File exists: {file_path}")
            else:
                print(f"❌ File does not exist: {file_path}")
                # Try to find similar files by looking for common Python file patterns
                # Extract the directory and filename from the missing file
                missing_dir = os.path.dirname(file_path)
                missing_filename = os.path.basename(file_path)
                
                # Look for files with similar names in allowed directories
                for allowed_dir in ALLOWED_PATHS:
                    if allowed_dir.startswith(missing_dir) or missing_dir.startswith(allowed_dir.rstrip('/')):
                        # Look for common Python file patterns
                        potential_files = [
                            f"{allowed_dir}{missing_filename}",
                            f"{allowed_dir}main.py",
                            f"{allowed_dir}app.py",
                            f"{allowed_dir}index.py"
                        ]
                        for potential_file in potential_files:
                            if _path_allowed(potential_file) and file_exists(potential_file, base):
                                existing_files.append(potential_file)
                                print(f"🎯 Found similar file: {potential_file}")
                                break
                        if existing_files:
                            break
        
        if existing_files:
            detected_files = existing_files
            print(f"✅ Using existing files: {detected_files}")
        else:
            print(f"❌ No existing files found, will ask for more context")
    
    # If we found files, use them directly
    if detected_files:
        print(f"✅ Found {len(detected_files)} files: {detected_files}")
        requested_files = detected_files
    else:
        # Fallback: Ask the AI what files it needs
        print(f"🤖 No files detected, asking AI what files it needs...")
        
        # Create a simple prompt to ask what files are needed
        simple_prompt = f"""You are analyzing an issue. Based on the title and description, what specific files do you need to see to understand and fix this issue?

Title: {title}
Description: {body}

Please respond with a JSON list of file paths you need, like:
{{"files_needed": ["path/to/file1.py", "path/to/file2.py"]}}

Only request files that are directly relevant to understanding and fixing the issue."""

        # Get the AI's response about what files it needs
        try:
            response = agent.client.chat.completions.create(
                model=agent.model,
                temperature=0,
                messages=[
                    {"role": "user", "content": simple_prompt},
                ],
            )
            ai_response = response.choices[0].message.content or ""
            print(f"🧠 AI response: {ai_response}")
            
            # Parse the AI's file requests
            try:
                ai_data = json.loads(ai_response)
                requested_files = ai_data.get("files_needed", [])
            except:
                # Fallback: try to extract file paths from the response
                file_pattern = r'["\']([^"\']*\.py)["\']'
                requested_files = re.findall(file_pattern, ai_response)
            
            print(f"📁 AI requested files: {requested_files}")
            
        except Exception as e:
            print(f"❌ Error asking AI for files: {e}")
            requested_files = []
    
    # 2) Check if requested files are in scope
    in_scope_files = []
    out_of_scope_files = []
    
    for file_path in requested_files:
        # Normalize the path
        normalized_path = _to_repo_relative(file_path)
        
        if _path_allowed(normalized_path):
            in_scope_files.append(normalized_path)
            print(f"✅ File in scope: {normalized_path}")
        else:
            out_of_scope_files.append(normalized_path)
            print(f"❌ File out of scope: {normalized_path}")
    
    # 3) If any files are out of scope, return error
    if out_of_scope_files:
        comment = f"""🤖 **TicketWatcher Analysis**

**Files Out of Scope**

The following files are not in the allowed paths:
{', '.join(out_of_scope_files)}

**Allowed paths:** {', '.join(ALLOWED_PATHS)}

**To fix this issue, please:**
1. Move the files to an allowed directory, or
2. Update the ALLOWED_PATHS configuration, or  
3. Create the issue in a repository where these files are allowed

I can only work with files in the allowed directories for security reasons."""
        
        add_issue_comment(number, comment)
        return None
    
    # 4) If no files requested or all out of scope, ask for more context
    if not in_scope_files:
        comment = f"""🤖 **TicketWatcher Analysis**

**No Files Identified**

I couldn't identify any specific files needed to fix this issue.

**To help me fix this issue, please provide:**

1. **A specific file path:**
   ```
   Target: src/main.py
   ```

2. **A traceback with file paths:**
   ```
   File "src/main.py", line 10, in my_function
       return some_value
   TypeError: unsupported operand type(s)
   ```

3. **Or mention the specific file:**
   - Just say "main.py" and I'll find it!

**Allowed paths:** {', '.join(ALLOWED_PATHS)}

I'm ready to help once I have the right context! 🚀"""
        
        add_issue_comment(number, comment)
        return None
    
    # 5) Fetch the in-scope files
    seed_snips: List[Dict[str, Any]] = []
    for file_path in in_scope_files:
        snip = _fetch_slice(file_path, base, None, AROUND_LINES)
        if snip:
            seed_snips.append(snip)
            print(f"✅ Fetched file: {file_path}")
        else:
            print(f"❌ Could not fetch file: {file_path}")
    
    if not seed_snips:
        comment = f"""🤖 **TicketWatcher Analysis**

**Files Not Found**

I identified the files you need, but they don't exist in the repository:
{', '.join(in_scope_files)}

**Please check:**
1. The file paths are correct
2. The files exist on the {base} branch
3. The files are in the allowed directories

**Allowed paths:** {', '.join(ALLOWED_PATHS)}"""
        
        add_issue_comment(number, comment)
        return None
    
    # 6) Call agent with the fetched files
    print(f"🤖 Calling agent with {len(seed_snips)} files...")
    
    def _fetch_callback(needs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for n in needs:
            path = n.get("path", "")
            line = n.get("line")
            symbol = n.get("symbol")
            around = int(n.get("around_lines") or AROUND_LINES)
            
            # Check if the requested file is in scope
            normalized_path = _to_repo_relative(path)
            if not _path_allowed(normalized_path):
                print(f"❌ Requested file out of scope: {normalized_path}")
                continue
                
            if symbol:
                sn = _fetch_symbol_slice(normalized_path, base, symbol, around)
            else:
                sn = _fetch_slice(normalized_path, base, line, around)
            if sn:
                results.append(sn)
                print(f"✅ Fetched additional file: {normalized_path}")
        return results

    result = agent.run_two_rounds(title, body, seed_snips, fetch_callback=_fetch_callback)

    # 7) Handle agent response
    if result.get("action") == "request_context":
        thinking = result.get("thinking", "No thinking process provided")
        reason = result.get("reason", "Need more context")
        needs = result.get("needs", [])
        
        # Show the thinking process
        print(f"🧠 AI Thinking: {thinking}")
        print(f"📝 Reason: {reason}")
        print(f"📁 Additional files needed: {needs}")
        
        # Create a JSON response for more context
        needs_json = []
        for need in needs:
            needs_json.append({
                "path": need.get("path", ""),
                "symbol": need.get("symbol"),
                "line": need.get("line"),
                "around_lines": need.get("around_lines", AROUND_LINES)
            })
        
        comment = f"""🤖 **TicketWatcher Analysis**

**AI Thinking Process:**
{thinking}

**Issue:** {reason}

**Files Currently Available:**
{', '.join([snip.get('path', '') for snip in seed_snips])}

**Additional Files Requested:**
```json
{json.dumps(needs_json, indent=2)}
```

**To help me fix this issue, please provide:**

1. **A specific file path:**
   ```
   Target: src/main.py
   ```

2. **A traceback with file paths:**
   ```
   File "src/main.py", line 10, in my_function
       return some_value
   TypeError: unsupported operand type(s)
   ```

3. **Or mention the specific file:**
   - Just say "main.py" and I'll find it!

**Allowed paths:** {', '.join(ALLOWED_PATHS)}
**Files must exist on branch:** {base}

I'm ready to help once I have the right context! 🚀"""
        
        add_issue_comment(number, comment)
        return None

    # 4) Validate diff against budgets/paths
    diff = result.get("diff", "")
    files_touched, changed_lines = _diff_stats(diff)
    if files_touched > MAX_FILES or changed_lines > MAX_LINES:
        add_issue_comment(number,
            f"⚠️ Proposed change exceeds budgets (files={files_touched}, lines={changed_lines}). "
            "Escalating to human review or try narrowing the scope."
        )
        return None

    # 5) Apply diff -> updated file texts
    try:
        updated_files = _apply_unified_diff(base, diff)
    except Exception as e:
        add_issue_comment(number, f"❌ Could not apply patch: {e}")
        return None

    # 6) Create branch, commit updates, open DRAFT PR
    branch = _mk_branch(number)
    create_branch(branch, base)
    for path, text in updated_files.items():
        create_or_update_file(
            path=path,
            content_text=text,
            message=f"agent: {title[:72]}",
            branch=branch,
        )

    # Get thinking process and notes
    thinking = result.get("thinking", "No thinking process provided")
    notes = result.get("notes", "")
    
    # Show the thinking process
    print(f"🧠 AI Thinking: {thinking}")
    print(f"📝 Notes: {notes}")
    print(f"📁 Files touched: {files_touched}")
    print(f"📏 Lines changed: {changed_lines}")
    
    pr_url, pr_number = create_pr(
        title=f"{PR_TITLE_PREF} #{number}",
        head=branch,
        base=base,
        body=f"""🤖 **Draft PR by TicketWatcher**

**AI Analysis:**
{thinking}

**Files:** {files_touched} • **Lines:** {changed_lines}
**Notes:** {notes}

**Files Currently Available:**
{', '.join([snip.get('path', '') for snip in seed_snips])}

This is a draft PR created by the TicketWatcher AI agent. Please review before merging.""",
        draft=True,
    )

     # Comment summary back on the PR (use PR number for /issues/{number}/comments)
    pr_comment = (
        f"✅ **Draft PR Created: {pr_url}**\n\n"
        f"**AI Thinking Process:**\n{thinking}\n\n"
        f"**Analysis Summary:**\n"
        f"- **Files touched:** {files_touched}\n"
        f"- **Lines changed:** {changed_lines}\n"
        f"- **Branch:** `{branch}`\n"
        f"- **Base:** `{base}`\n\n"
        f"**Notes:** {notes}\n\n"
        f"The AI agent has analyzed the issue and proposed a fix. Please review the PR before merging! 🚀"
    )
    add_issue_comment(pr_number, pr_comment)

    # (Optional) also notify the original issue if you want
    try:
        add_issue_comment(number, f"Draft PR opened: {pr_url}")
    except Exception as e:
        print(f"[warn] could not comment on issue #{number}: {e}")

    return pr_url

def handle_issue_comment_event(event: Dict[str, Any]) -> Optional[str]:
    """
    Optional: keep your '/agent fix' comment trigger. It now just runs the same agent path,
    using the comment body as extra ticket context.
    """
    action = event.get("action")
    if action != "created":
        return None

    issue = event.get("issue") or {}
    number = issue.get("number")
    comment_body = (event.get("comment") or {}).get("body", "")

    if not comment_body.strip().lower().startswith("/agent fix"):
        return None

    # Reuse the main flow by pretending the comment text is appended to the body
    issue_copy = dict(issue)
    issue_copy["body"] = (issue.get("body") or "") + "\n\n" + comment_body
    fake_event = dict(event)
    fake_event["issue"] = issue_copy
    return handle_issue_event(fake_event)
