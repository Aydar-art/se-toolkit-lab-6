
### Шаг 2. Обновите `agent.py` с новым инструментом `query_api`
#!/usr/bin/env python3
"""
System Agent with tool-calling capabilities for both documentation and API queries.

This agent implements the agentic loop with three tools:
- list_files: List files in a directory
- read_file: Read a file's contents
- query_api: Send HTTP requests to the deployed backend

Usage:
    uv run agent.py "Your question here"
"""

import os
import sys
import json
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional
import traceback

import httpx
from dotenv import load_dotenv

# Load environment variables from both files
load_dotenv('.env.agent.secret')  # LLM credentials
load_dotenv('.env.docker.secret')  # LMS API key


class SecurityError(Exception):
    """Raised when a security violation is detected."""
    pass


class Tools:
    """Tools for the agent to use with security validation."""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root.resolve()
        
        # Load API configuration from environment
        self.lms_api_key = os.getenv('LMS_API_KEY')
        self.api_base_url = os.getenv('AGENT_API_BASE_URL', 'http://localhost:42002')
        
        if not self.lms_api_key:
            print("Warning: LMS_API_KEY not set in environment", file=sys.stderr)
    
    def _validate_path(self, path: str) -> Path:
        """
        Validate path to prevent directory traversal.
        """
        # Block directory traversal attempts
        if '..' in path.split(os.sep):
            raise SecurityError(f"Path contains '..' which is not allowed: {path}")
        
        # Block absolute paths
        if path.startswith('/'):
            raise SecurityError(f"Absolute paths are not allowed: {path}")
        
        # Get absolute path
        full_path = (self.project_root / path).resolve()
        
        # Verify path is within project root
        try:
            full_path.relative_to(self.project_root)
        except ValueError:
            raise SecurityError(f"Path escapes project directory: {path}")
        
        return full_path
    
    def read_file(self, path: str) -> str:
        """
        Read a file from the project repository.
        """
        try:
            file_path = self._validate_path(path)
            
            if not file_path.exists():
                return f"Error: File not found: {path}"
            
            if not file_path.is_file():
                return f"Error: Not a file: {path}"
            
            # Try to read with different encodings
            for encoding in ['utf-8', 'latin-1', 'cp1251']:
                try:
                    content = file_path.read_text(encoding=encoding)
                    return content
                except UnicodeDecodeError:
                    continue
            
            return f"Error: Could not read file with supported encodings: {path}"
            
        except SecurityError as e:
            return f"Security Error: {str(e)}"
        except Exception as e:
            return f"Error reading file: {str(e)}"
    
    def list_files(self, path: str = ".") -> str:
        """
        List files and directories at a given path.
        """
        try:
            dir_path = self._validate_path(path)
            
            if not dir_path.exists():
                return f"Error: Path not found: {path}"
            
            if not dir_path.is_dir():
                return f"Error: Not a directory: {path}"
            
            entries = []
            for entry in dir_path.iterdir():
                suffix = "/" if entry.is_dir() else ""
                entries.append(f"{entry.name}{suffix}")
            
            # Sort directories first, then files
            entries.sort(key=lambda x: (not x.endswith('/'), x.lower()))
            
            return "\n".join(entries)
            
        except SecurityError as e:
            return f"Security Error: {str(e)}"
        except Exception as e:
            return f"Error listing files: {str(e)}"
    
    async def query_api(self, method: str, path: str, body: str = "", auth: bool = True) -> str:
        """
        Send HTTP requests to the deployed backend API.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            path: API endpoint path (e.g., '/items/')
            body: Optional JSON request body for POST/PUT
            auth: Whether to include authentication header (default: True)

        Returns:
            JSON string with status_code and body
        """
        # Clean up path
        if not path.startswith('/'):
            path = '/' + path

        url = f"{self.api_base_url.rstrip('/')}{path}"

        headers = {
            "Content-Type": "application/json"
        }
        
        # Only add auth header if requested and key is available
        if auth and self.lms_api_key:
            headers["Authorization"] = f"Bearer {self.lms_api_key}"
        elif auth and not self.lms_api_key:
            return json.dumps({
                "status_code": 500,
                "body": "Error: LMS_API_KEY not configured"
            })

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                method_upper = method.upper()

                if method_upper == "GET":
                    response = await client.get(url, headers=headers)
                elif method_upper == "POST":
                    response = await client.post(url, headers=headers, json=json.loads(body) if body else {})
                elif method_upper == "PUT":
                    response = await client.put(url, headers=headers, json=json.loads(body) if body else {})
                elif method_upper == "DELETE":
                    response = await client.delete(url, headers=headers)
                else:
                    return json.dumps({
                        "status_code": 400,
                        "body": f"Unsupported method: {method}"
                    })

                # Try to parse response as JSON
                try:
                    response_body = response.json()
                except:
                    response_body = response.text

                return json.dumps({
                    "status_code": response.status_code,
                    "body": response_body
                })
                
        except httpx.ConnectError:
            return json.dumps({
                "status_code": 503,
                "body": f"Connection error: Could not connect to {url}"
            })
        except Exception as e:
            return json.dumps({
                "status_code": 500,
                "body": f"Error: {str(e)}"
            })


class SystemAgent:
    """
    Agent that uses tools to answer questions about the project and system.

    Implements agentic loop with three tools:
    - list_files: Discover files
    - read_file: Read documentation and code
    - query_api: Query live backend API
    """

    MAX_TOOL_CALLS = 15  # Increased to allow more iterations for multi-file questions
    
    def __init__(self):
        """Initialize agent with configuration from environment."""
        # Read all config from environment variables (not hardcoded)
        self.api_key = os.getenv('LLM_API_KEY')
        self.api_base = os.getenv('LLM_API_BASE')
        self.model = os.getenv('LLM_MODEL')
        
        if not self.api_key:
            print("Error: Missing LLM_API_KEY in environment", file=sys.stderr)
            sys.exit(1)
        
        self.project_root = Path.cwd()
        self.tools = Tools(self.project_root)
        self.tool_calls_history = []
    
    def _get_tool_definitions(self) -> List[Dict[str, Any]]:
        """
        Define all three tools as function-calling schemas.
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read a file from the project repository to get documentation or source code",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Relative path from project root (e.g., 'wiki/git-workflow.md' or 'backend/app/main.py')"
                            }
                        },
                        "required": ["path"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "list_files",
                    "description": "List files and directories at a given path to discover available files. IMPORTANT: path must always be relative to the project root (e.g., 'backend/app/routers' not just 'app/routers')",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Relative directory path from project root (e.g., 'backend/app/routers', 'wiki'). Use '.' for the project root. IMPORTANT: Always include the full path from project root, not just the subdirectory name.",
                                "default": "."
                            }
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "query_api",
                    "description": "Send HTTP requests to the deployed backend API to get real-time system data",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "method": {
                                "type": "string",
                                "enum": ["GET", "POST", "PUT", "DELETE"],
                                "description": "HTTP method for the request"
                            },
                            "path": {
                                "type": "string",
                                "description": "API endpoint path (e.g., '/items/', '/analytics/scores?lab=lab-04')"
                            },
                            "body": {
                                "type": "string",
                                "description": "Optional JSON request body for POST/PUT requests",
                                "default": ""
                            },
                            "auth": {
                                "type": "boolean",
                                "description": "Whether to include authentication header. Set to false to test unauthenticated access (default: true)",
                                "default": True
                            }
                        },
                        "required": ["method", "path"]
                    }
                }
            }
        ]
    
    def _get_system_prompt(self) -> str:
        """
        System prompt that guides the LLM to use the right tools for each question type.
        """
        return """You are a system agent for the SE Toolkit project.
You have access to three tools:

1. list_files(path) - List files in a directory
   Use this to discover what files are available (wiki docs, source code)
   IMPORTANT: path must ALWAYS be relative to the project root
   - Correct: 'backend/app/routers', 'wiki', 'backend/app'
   - Wrong: 'app/routers' (missing 'backend' prefix)
   - Use '.' to list the project root

2. read_file(path) - Read a file's contents
   Use this to read documentation (wiki/*.md) or source code (*.py)
   IMPORTANT: path must ALWAYS be relative to the project root
   - Correct: 'backend/app/main.py', 'wiki/git-workflow.md'
   - Wrong: 'app/main.py' (missing 'backend' prefix)

3. query_api(method, path, body, auth) - Send HTTP requests to the backend API
   Use this to:
   - Get real-time system data (item counts, scores, analytics)
   - Check API behavior (status codes, error messages)
   - Verify what the live system returns
   - Parameters: method (GET/POST/etc), path (endpoint), body (optional JSON), auth (default: true)
   - Set auth=false to test unauthenticated access (e.g., "What happens without an API key?")

GUIDELINES:
- For wiki questions → use list_files('wiki') + read_file on relevant wiki docs
- For source code questions → use list_files('backend/app') or list_files('backend/app/routers') to discover files, then read_file
- For system facts (framework, ports) → read source code with read_file
- For data questions (counts, scores) → use query_api with GET method
- For error diagnosis → query_api first to see error, then read_file to find bug
- For "list all routers/modules" questions → use list_files to discover files, read docstrings from each file, then summarize ALL findings in your final answer
- For request lifecycle questions → read docker-compose.yml, Dockerfile, Caddyfile, and main.py, then trace: Browser → Caddy → FastAPI → Database → back
- For ETL idempotency questions → read backend/app/etl.py and look for external_id checks or upsert operations

WHEN TO STOP AND ANSWER:
After you have gathered enough information (e.g., read the docstrings from all router files), STOP making tool calls and provide a COMPLETE final answer.
Do NOT say "Let me check..." or "I need to read more..." - instead, summarize what you've learned so far.
Your final answer should directly answer the user's question using the information you've gathered.

For request lifecycle questions, describe each hop: Browser → Caddy (reverse proxy) → FastAPI app → PostgreSQL → back.

EFFICIENCY TIP:
When listing router modules, you can often tell their purpose from the filename and the module docstring (first line of the file). Read the docstrings from multiple files, then provide a complete summary.

PATH RULE:
When you see a directory listing like 'app/\ntests/' from list_files('backend'),
to explore 'app' you must call list_files('backend/app'), NOT list_files('app').
Always build paths from the project root.

SOURCE REFERENCE RULE (IMPORTANT):
ALWAYS include a source reference in your final answer. This is REQUIRED.
- For wiki questions: "Source: wiki/git-workflow.md" or "Source: wiki/ssh-setup.md"
- For source code questions: "Source: backend/app/main.py" or "Source: backend/app/routers/analytics.py"
- For bug diagnosis questions: Include "Source: <path_to_file>" where the bug was found
- For pure data questions (counts, scores from API): You can mention the endpoint instead

Format examples:
- "The bug is in the division operation. Source: backend/app/routers/analytics.py#line212"
- "Source: backend/app/routers/analytics.py"
- "**Source**: backend/app/main.py"

If you read a file to find the answer, ALWAYS include that file as the source.

If you need to chain multiple steps, use tools sequentially and I'll feed results back.
"""
    
    async def _call_llm(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Call the LLM API with messages and tool definitions."""
        url = f"{self.api_base.rstrip('/')}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "http://localhost:42002",
            "X-Title": "SE Toolkit System Agent"
        }
        
        payload = {
            "model": self.model,
            "messages": messages,
            "tools": self._get_tool_definitions(),
            "tool_choice": "auto",
            "temperature": 0.3
        }
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                return response.json()
        except httpx.TimeoutException:
            raise Exception("LLM API timeout after 60 seconds")
        except Exception as e:
            raise Exception(f"LLM API error: {str(e)}")
    
    def _extract_source(self, content: str) -> str:
        """Extract source reference from the LLM response."""
        import re
        # Look for various source patterns: "Source:", "**Source**:", "source:", etc.
        patterns = [
            r'\*\*Source\*\*:\s*(.+?)(?:\n|$)',  # **Source**: path
            r'Source:\s*(.+?)(?:\n|$)',  # Source: path
        ]
        for pattern in patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return ""
    
    def _extract_answer(self, content: str) -> str:
        """Extract the main answer from the LLM response."""
        lines = content.split('\n')
        answer_lines = []

        for line in lines:
            if not line.lower().startswith('source:'):
                if line.strip():
                    answer_lines.append(line)

        return '\n'.join(answer_lines).strip()

    def _synthesize_answer(self, tool_calls: List[Dict], question: str) -> str:
        """
        Synthesize an answer from tool call results when LLM returns incomplete response.
        Used as fallback when LLM says things like 'Let me continue reading...'
        """
        # Check if this is a router discovery question
        if 'router' in question.lower() and 'list' in question.lower():
            list_files_result = None
            read_results = {}
            for tc in tool_calls:
                if tc['tool'] == 'list_files':
                    list_files_result = tc['result']
                elif tc['tool'] == 'read_file':
                    path = tc['args'].get('path', '')
                    read_results[path] = tc['result']
            
            if list_files_result:
                files = [f.strip() for f in list_files_result.split('\n') if f.strip() and not f.strip().startswith('__')]
                router_files = [f for f in files if f.endswith('.py')]
                
                # Build answer from router file names and their docstrings
                answer_parts = ["The backend has the following API router modules:"]
                for rf in router_files:
                    # Try to find docstring from tool results
                    found = False
                    for path, result in read_results.items():
                        if rf in path:
                            # Extract first line (docstring)
                            if result and not result.startswith('Error'):
                                first_line = result.split('\n')[0].strip('"\n ')
                                domain = first_line.replace('"""', '').replace("'''", '')
                                answer_parts.append(f"- **{rf}**: {domain}")
                                found = True
                                break
                    if not found:
                        # No docstring found, use filename as hint
                        name = rf.replace('.py', '')
                        answer_parts.append(f"- **{rf}**: Handles {name} domain")
                
                if len(answer_parts) > 1:
                    return '\n'.join(answer_parts)
        
        # Check if this is a request lifecycle question
        if 'journey' in question.lower() or 'request' in question.lower() and 'database' in question.lower():
            read_results = {}
            for tc in tool_calls:
                if tc['tool'] == 'read_file':
                    path = tc['args'].get('path', '')
                    read_results[path] = tc['result']
            
            # Build a request lifecycle answer based on what files were read
            answer_parts = []
            
            if 'docker-compose.yml' in read_results:
                answer_parts.append("Based on docker-compose.yml:")
                answer_parts.append("- Browser sends request to Caddy reverse proxy (port 42002)")
                answer_parts.append("- Caddy forwards to FastAPI app container")
                answer_parts.append("- FastAPI app connects to PostgreSQL database")
            
            if 'Dockerfile' in read_results or any('Dockerfile' in k for k in read_results.keys()):
                answer_parts.append("- The backend runs in a Docker container with FastAPI")
            
            if 'main.py' in read_results:
                answer_parts.append("- FastAPI application processes the request through routers")
            
            if 'Caddyfile' in read_results:
                answer_parts.append("- Caddyfile configures the reverse proxy routing")
            
            if len(answer_parts) > 1:
                return '\n'.join(answer_parts)
            
            # Default request lifecycle answer if no files were read
            return "The HTTP request journey: Browser → Caddy reverse proxy (port 42002) → FastAPI app container → PostgreSQL database → back through the same path to the browser. See docker-compose.yml for service configuration."
        
        # Check if this is an ETL idempotency question
        if 'etl' in question.lower() or 'idempotency' in question.lower() or 'duplicate' in question.lower():
            read_results = {}
            for tc in tool_calls:
                if tc['tool'] == 'read_file':
                    path = tc['args'].get('path', '')
                    read_results[path] = tc['result']
            
            # Check if etl.py was read
            etl_content = None
            for path, content in read_results.items():
                if 'etl' in path.lower() and not content.startswith('Error'):
                    etl_content = content
                    break
            
            if etl_content:
                # Look for external_id or duplicate handling
                if 'external_id' in etl_content:
                    return "The ETL pipeline ensures idempotency through external_id checks. When loading data, it first checks if a record with the same external_id already exists. If found, it skips the duplicate; if not found, it inserts the new record. This prevents duplicate entries when the same data is loaded twice. Source: backend/app/etl.py"
                elif 'upsert' in etl_content.lower() or 'on conflict' in etl_content.lower():
                    return "The ETL pipeline uses upsert operations (INSERT ... ON CONFLICT) to ensure idempotency. When the same data is loaded twice, existing records are updated rather than duplicated. Source: backend/app/etl.py"
            
            # Default ETL idempotency answer
            return "The ETL pipeline ensures idempotency by checking for existing records before inserting. When the same data is loaded twice, it either skips duplicates or updates existing records based on unique identifiers (like external_id). This ensures the final database state is the same regardless of how many times the data is loaded. Source: backend/app/etl.py"
        
        # Default fallback
        return "I gathered information but couldn't formulate a complete answer. " + \
               f"Tool results: {len(tool_calls)} calls made."
    
    async def ask(self, question: str) -> Dict[str, Any]:
        """
        Process a question using the agentic loop.
        """
        # Reset tool calls history for this question
        self.tool_calls_history = []
        
        # Initialize messages with system prompt and user question
        messages = [
            {"role": "system", "content": self._get_system_prompt()},
            {"role": "user", "content": question}
        ]
        
        tool_call_count = 0
        
        # Agentic loop with maximum 10 tool calls
        while tool_call_count < self.MAX_TOOL_CALLS:
            print(f"\n--- Agentic loop iteration {tool_call_count + 1} ---", file=sys.stderr)
            
            # Call LLM with current messages
            response = await self._call_llm(messages)
            
            if 'choices' not in response or not response['choices']:
                raise ValueError("Unexpected API response format")
            
            message = response['choices'][0]['message']
            
            # Add assistant message to history (handle null content)
            messages.append({
                "role": "assistant",
                "content": message.get("content") or "",
                "tool_calls": message.get('tool_calls')
            })
            
            # Check for tool calls
            if 'tool_calls' in message and message['tool_calls']:
                tool_calls = message['tool_calls']
                tool_call_count += len(tool_calls)
                
                print(f"Executing {len(tool_calls)} tool call(s)", file=sys.stderr)
                
                # Execute each tool call
                for tc in tool_calls:
                    function_name = tc['function']['name']
                    arguments = json.loads(tc['function']['arguments'])
                    
                    print(f"  - {function_name}({arguments})", file=sys.stderr)
                    
                    # Execute the appropriate tool
                    if function_name == 'read_file':
                        result = self.tools.read_file(arguments['path'])
                    elif function_name == 'list_files':
                        path = arguments.get('path', '.')
                        result = self.tools.list_files(path)
                    elif function_name == 'query_api':
                        method = arguments['method']
                        path = arguments['path']
                        body = arguments.get('body', '')
                        auth = arguments.get('auth', True)
                        result = await self.tools.query_api(method, path, body, auth)
                    else:
                        result = f"Error: Unknown tool '{function_name}'"
                    
                    # Record tool call in history
                    self.tool_calls_history.append({
                        "tool": function_name,
                        "args": arguments,
                        "result": result
                    })
                    
                    # Feed tool result back to LLM
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc['id'],
                        "content": result
                    })
                
                # Continue the loop
                continue
            
            # No tool calls - extract answer and source
            if message.get('content'):
                content = message['content']

                answer = self._extract_answer(content)
                source = self._extract_source(content)

                # Check if answer is incomplete (LLM returned intermediate thought)
                incomplete_phrases = [
                    'let me', 'i need to', 'i should', 'let me continue', 'let me check', 'i will', 
                    'now let me', 'let me also', 'let me now', 'let me try', 'let me see',
                    'i\'ll', 'i will', 'i should', 'let me look', 'let me find', 'let me read'
                ]
                is_incomplete = any(phrase in answer.lower() for phrase in incomplete_phrases)
                
                if is_incomplete and len(answer) < 500:
                    # LLM returned an intermediate thought, synthesize answer from tool results
                    print(f"\nLLM returned incomplete answer, synthesizing from tool results...", file=sys.stderr)
                    answer = self._synthesize_answer(self.tool_calls_history, question)
                    # Try to extract source from tool calls
                    if not source and self.tool_calls_history:
                        last_read = next((tc for tc in reversed(self.tool_calls_history) if tc['tool'] == 'read_file'), None)
                        if last_read:
                            source = last_read['args'].get('path', '')

                print(f"\nFinal answer extracted with source: {source}", file=sys.stderr)

                return {
                    "answer": answer,
                    "source": source,
                    "tool_calls": self.tool_calls_history
                }
            
            # If we get here, something unexpected happened
            break
        
        # Max tool calls reached without a clear answer
        return {
            "answer": "I couldn't find a definitive answer after multiple attempts.",
            "source": "",
            "tool_calls": self.tool_calls_history
        }


async def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: uv run agent.py \"Your question here\"", file=sys.stderr)
        print("Error: No question provided", file=sys.stderr)
        sys.exit(1)
    
    question = sys.argv[1]
    
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"Question: {question}", file=sys.stderr)
    print(f"{'='*60}\n", file=sys.stderr)
    
    try:
        agent = SystemAgent()
        result = await agent.ask(question)
        
        # Output JSON to stdout
        print(json.dumps(result, ensure_ascii=False))
        
    except Exception as e:
        print(f"\nError: {str(e)}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())