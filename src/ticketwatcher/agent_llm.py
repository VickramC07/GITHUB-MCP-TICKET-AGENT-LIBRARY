import os
import json
import re
from string import Template
from typing import List, Dict, Any, Optional, Tuple
from openai import OpenAI


class TicketWatcherAgent:
    """
    Minimal agent wrapper that:
      - Builds the system/user prompts
      - Calls the LLM
      - Enforces the JSON-only response contract
      - Supports an iterative "request_context -> fetch snippets -> propose_patch" loop

    Usage (pseudo):
      agent = TicketWatcherAgent()
      result = agent.run(
          ticket_title="...",
          ticket_body="...",
          snippets=[{"path":"src/app/auth.py","start_line":1,"end_line":120,"code": "..."}]
      )
      if result["action"] == "request_context":
          # fetch the requested slices and call run(...) again, or do a second round with agent.run_round(...)
      elif result["action"] == "propose_patch":
          # validate + apply the unified diff in result["diff"]
    """

    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        allowed_paths: Optional[List[str]] = None,
        max_files: int = 4,
        max_total_lines: int = 200,
        default_around_lines: int = 60,
        route_hint: str = "llm",
        system_prompt: Optional[str] = None,
        user_prompt_template: Optional[str] = None,
    ):
        self.model = model or os.getenv("TICKETWATCHER_MODEL", "gpt-4o-mini")
        self.client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
        self.allowed_paths = allowed_paths or self._parse_allowed_paths_env(
            os.getenv("ALLOWED_PATHS", "src/,app/")
        )
        self.max_files = int(os.getenv("MAX_FILES", str(max_files)))
        self.max_total_lines = int(os.getenv("MAX_LINES", str(max_total_lines)))
        self.default_around_lines = int(
            os.getenv("DEFAULT_AROUND_LINES", str(default_around_lines))
        )
        self.route_hint = os.getenv("ROUTE", route_hint)

        # Prompts
        self.sysprompt = system_prompt or (
            "You are TicketFix, an intelligent automated code-fixing agent.\n\n"
            "## THINKING PROCESS\n"
            "Before responding, analyze the issue systematically:\n"
            "1. **ANALYZE** the issue for error messages, file paths, function names, context clues\n"
            "2. **DETECT** potential file locations from function names, domain clues, partial paths\n"
            "3. **REASON** about what information you need to solve the problem\n"
            "4. **PLAN** your approach strategically\n\n"
            "Return EXACTLY ONE JSON object and NOTHING ELSE (no prose, no code fences):\n\n"
            "1) Ask for more context:\n"
            "{\n"
            '  "action": "request_context",\n'
            '  "needs": [\n'
            '    { "path": "string", "symbol": "string|null", "line": "integer|null", "around_lines": "integer" }\n'
            "  ],\n"
            '  "reason": "string",\n'
            '  "thinking": "string (your reasoning process)"\n'
            "}\n\n"
            "2) Propose a minimal patch:\n"
            "{\n"
            '  "action": "propose_patch",\n'
            '  "format": "unified_diff",\n'
            '  "diff": "string (standard unified diff: --- a/<path> / +++ b/<path> …)",\n'
            '  "files_touched": ["string", ...],\n'
            '  "estimated_changed_lines": "integer",\n'
            '  "notes": "string",\n'
            '  "thinking": "string (your reasoning process)"\n'
            "}\n\n"
            "## ENHANCED RULES\n"
            "- **Smart Context Detection**: Even if no explicit file paths are given, infer likely locations\n"
            "- **Progressive Information Gathering**: Start broad, then narrow down\n"
            "- **Thinking Transparency**: Always explain your reasoning in the 'thinking' field\n"
            "- **Strategic Information**: Request the most valuable information first\n"
            "- **Constraint Awareness**: Respect max_files, max_lines, allowed_paths\n"
            "- **Minimal Changes**: Prefer the smallest safe fix\n"
            "- **File Analysis**: If you have access to the target file, analyze it first before asking for more context\n"
            "- **Smart Requests**: Only request additional files if you need to understand imports, dependencies, or related functionality\n\n"
            "## CONTEXT DETECTION STRATEGIES\n"
            "- Look for function names: 'get_user_profile' → likely in auth/user files\n"
            "- Look for error patterns: 'KeyError: name' → likely dict access issues\n"
            "- Look for domain clues: 'authentication' → likely auth.py files\n"
            "- Look for partial paths: 'auth.py' → try src/app/auth.py, app/auth.py\n"
            "- Look for import errors: 'ModuleNotFoundError' → check import paths\n\n"
            "Remember: You're not just looking for explicit file paths - you're detecting context and inferring likely locations!"
        )

        self.user_template = user_prompt_template or """
# TICKET ANALYSIS REQUEST

## ISSUE DETAILS
**Title:** $ticket_title
**Description:**
$ticket_body_trimmed

## CONSTRAINTS
- **Allowed Paths:** $allowed_paths_csv
- **Max Files:** $max_files
- **Max Lines:** $max_total_lines
- **Context Window:** $around_lines lines around target

## CURRENT CONTEXT
$snippets_block

## YOUR TASK
Analyze this issue and either:

**A) REQUEST MORE CONTEXT** if you need additional information:
```json
{
  "action": "request_context",
  "needs": [
    { "path": "src/app/auth.py", "symbol": "get_user_profile", "line": null, "around_lines": 60 }
  ],
  "reason": "I need to see the get_user_profile function to understand the KeyError",
  "thinking": "The error mentions KeyError: 'name' in get_user_profile. I should examine this function and understand how user data is structured."
}
```

**B) PROPOSE A FIX** if you have enough information:
```json
{
  "action": "propose_patch",
  "format": "unified_diff",
  "diff": "--- a/src/app/auth.py\\n+++ b/src/app/auth.py\\n@@ -10,7 +10,7 @@ def get_user_profile(user_id):\\n-    name = user[\\\"name\\\"]\\n+    name = user.get(\\\"name\\\", \\\"\\\")\\n",
  "files_touched": ["src/app/auth.py"],
  "estimated_changed_lines": 1,
  "notes": "Fixed KeyError by using .get() with default value",
  "thinking": "The issue is a KeyError when accessing user['name']. Using .get() with a default empty string will prevent the crash."
}
```

## ENHANCED ANALYSIS TIPS
1. **Look for patterns** in the issue description
2. **Infer file locations** from context clues
3. **Think strategically** about what information you need
4. **Explain your reasoning** in the thinking field
5. **Be proactive** in context detection

Remember: You're an intelligent agent - use your reasoning to detect context even when it's not explicitly provided!
"""  
        

    # ---------- public entry points ----------

    def run(
        self,
        ticket_title: str,
        ticket_body: str,
        snippets: List[Dict[str, Any]],
        trim_body_chars: int = 3000,
    ) -> Dict[str, Any]:
        """
        Single round call. Provide any snippets you already have (can be []),
        returns either request_context or propose_patch dict.
        """
        user = self._build_user_prompt(
            ticket_title=ticket_title,
            ticket_body=ticket_body,
            snippets=snippets,
            trim_body_chars=trim_body_chars,
        )
        return self._call_llm(self.sysprompt, user)

    def run_two_rounds(
        self,
        ticket_title: str,
        ticket_body: str,
        seed_snippets: List[Dict[str, Any]],
        fetch_callback,
        # fetch_callback(needs: List[Dict]) -> List[snippet-dicts]
        trim_body_chars: int = 3000,
    ) -> Dict[str, Any]:
        """
        Convenience helper:
          - round 1 with seed snippets
          - if request_context, uses fetch_callback to fetch more slices
          - round 2 with augmented snippets
        Returns the final JSON dict (request_context or propose_patch).
        """
        result = self.run(ticket_title, ticket_body, seed_snippets, trim_body_chars)
        if result.get("action") == "request_context":
            needs = self._sanitize_needs(result.get("needs", []))
            if not needs:
                return result  # nothing to fetch; return as-is
            more = fetch_callback(needs)
            all_snips = seed_snippets + (more or [])
            return self.run(ticket_title, ticket_body, all_snips, trim_body_chars)
        return result

    # ---------- prompt building ----------

    def _build_user_prompt(
        self,
        ticket_title: str,
        ticket_body: str,
        snippets: List[Dict[str, Any]],
        trim_body_chars: int = 3000,
    ) -> str:
        ticket_body_trimmed = (ticket_body or "")[:trim_body_chars]
        snippets_block = self._format_snippets_block(snippets)

        return Template(self.user_template).safe_substitute(
            ticket_title=ticket_title or "",
            ticket_body_trimmed=ticket_body_trimmed,
            allowed_paths_csv=",".join(self.allowed_paths),
            max_files=self.max_files,
            max_total_lines=self.max_total_lines,
            around_lines=self.default_around_lines,
            route_hint=self.route_hint,
            snippets_block=snippets_block,
        )

    @staticmethod
    def _format_snippets_block(snippets: List[Dict[str, Any]]) -> str:
        parts = []
        for s in snippets:
            path = s.get("path", "")
            start = int(s.get("start_line", 1))
            end = int(s.get("end_line", max(start, start)))
            code = s.get("code", "")
            parts.append(
                f"--- path: {path}\n--- start_line: {start}\n--- end_line: {end}\n--- code:\n{code}\n"
            )
        return "\n".join(parts) if parts else ""

    # ---------- LLM call & parsing ----------

    def _call_llm(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        resp = self.client.chat.completions.create(
            model=self.model,
            temperature=0,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        raw = (resp.choices[0].message.content or "").strip()

        # Be defensive: strip code fences if the model added them
        raw = self._strip_code_fences(raw)

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # Force a request for context if format is bad (keeps runner simple)
            return {
                "action": "request_context",
                "needs": [],
                "reason": "Model did not return valid JSON. Please provide exact slices you need.",
                "raw": raw[:2000],
            }

        # Validate minimal contract
        action = data.get("action")
        if action not in {"request_context", "propose_patch"}:
            return {
                "action": "request_context",
                "needs": [],
                "reason": "Missing or invalid 'action'. Expected 'request_context' or 'propose_patch'.",
                "raw": raw[:2000],
            }
        return data

    @staticmethod
    def _strip_code_fences(s: str) -> str:
        # Remove ```json ... ``` or ``` ... ```
        s = s.strip()
        if s.startswith("```"):
            s = re.sub(r"^```(?:json)?\s*", "", s)
            s = re.sub(r"\s*```$", "", s)
        return s.strip()

    # ---------- helpers ----------

    def _sanitize_needs(self, needs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Ensure each need has path within allowed_paths and sane around_lines."""
        cleaned = []
        for n in needs or []:
            path = (n or {}).get("path", "")
            if not self._path_allowed(path):
                continue
            around = int((n.get("around_lines") or self.default_around_lines))
            around = max(10, min(around, self.default_around_lines))  # cap at default
            out = {
                "path": path,
                "symbol": n.get("symbol"),
                "line": n.get("line"),
                "around_lines": around,
            }
            cleaned.append(out)
        return cleaned

    def _path_allowed(self, path: str) -> bool:
        if not path:
            return False
        return any(path.startswith(pfx) for pfx in self.allowed_paths)

    def detect_context_from_issue(self, title: str, body: str) -> List[Tuple[str, Optional[int]]]:
        """
        Enhanced context detection from issue title and body.
        Returns list of (path, line) tuples.
        """
        detected_paths = []
        
        # Enhanced patterns for context detection
        patterns = [
            # Explicit file paths
            r'File\s+"([^"]+)"\s*,\s*line\s+(\d+)',
            r'File\s+([^\s,]+)\s*,\s*line\s+(\d+)',
            # Partial file names
            r'\b(\w+\.py)\b',
            r'\b(\w+\.js)\b',
            r'\b(\w+\.ts)\b',
            # Function/class names that might indicate files
            r'\b(get_user|auth|login|user|profile|main|app|index|init)\b',
            # Import statements
            r'from\s+([^\s]+)\s+import',
            r'import\s+([^\s]+)',
        ]
        
        text = f"{title} {body}".lower()
        
        # First, try to find explicit file references
        for pattern in patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                if len(match.groups()) >= 2:
                    # Has line number
                    path = match.group(1)
                    line = int(match.group(2))
                else:
                    # No line number
                    path = match.group(1)
                    line = None
                
                # Convert to full paths
                full_paths = self._expand_partial_path(path)
                for full_path in full_paths:
                    if self._path_allowed(full_path):
                        detected_paths.append((full_path, line))
        
        # If no specific files found, try to find files in allowed directories
        if not detected_paths:
            print(f"🔍 No specific files detected, searching allowed directories: {self.allowed_paths}")
            
            # Enhanced general file detection
            print(f"🔍 No specific files detected, trying general file detection...")
            for allowed_dir in self.allowed_paths:
                # Look for common Python file patterns
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
                    if self._path_allowed(file_path):
                        detected_paths.append((file_path, None))
                        print(f"🎯 Added general file: {file_path}")
                        break  # Only add one file per directory
        
        return detected_paths[:5]  # Limit to 5 paths

    def _expand_partial_path(self, partial_path: str) -> List[str]:
        """Expand partial file names to full paths"""
        if "/" in partial_path:
            return [partial_path]  # Already a full path
        
        # Common expansions
        expansions = []
        for allowed_path in self.allowed_paths:
            if allowed_path.endswith("/"):
                expansions.append(f"{allowed_path}{partial_path}")
            else:
                expansions.append(f"{allowed_path}/{partial_path}")
        
        return expansions

    def _path_allowed(self, path: str) -> bool:
        """Check if path is in allowed paths"""
        if not path:
            return False
        return any(path.startswith(pfx) for pfx in self.allowed_paths)

    @staticmethod
    def _parse_allowed_paths_env(s: str) -> List[str]:
        parts = [p.strip() for p in (s or "").split(",") if p.strip()]
        # normalize to end with slash where appropriate
        norm = []
        for p in parts:
            norm.append(p if p.endswith("/") else (p + ("/" if "." not in p else "")))
        return norm or ["src/"]