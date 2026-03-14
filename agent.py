#!/usr/bin/env python3
"""
Documentation Agent with tool-calling capabilities.

This agent implements the agentic loop:
1. Send question + tool definitions to LLM
2. If tool calls requested → execute tools and feed results back
3. If no tool calls → extract answer and source, output JSON

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

# Load environment variables
load_dotenv('.env.agent.secret')


class SecurityError(Exception):
    """Raised when a security violation is detected."""
    pass


class Tools:
    """Tools for the agent to use with security validation."""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root.resolve()
    
    def _validate_path(self, path: str) -> Path:
        """
        Validate path to prevent directory traversal.
        
        Security requirements:
        - Must not read files outside the project directory
        - No `../` traversal allowed
        - No absolute paths
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
        
        Args:
            path: Relative path from project root
            
        Returns:
            File contents or error message
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
        
        Args:
            path: Relative directory path from project root
            
        Returns:
            Newline-separated listing of entries
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


class DocumentationAgent:
    """
    Agent that uses tools to answer questions about the project.
    
    Implements agentic loop that executes tool calls and feeds results back.
    """
    
    MAX_TOOL_CALLS = 10
    
    def __init__(self):
        """Initialize agent with configuration from environment."""
        self.api_key = os.getenv('LLM_API_KEY')
        self.api_base = os.getenv('LLM_API_BASE')
        self.model = os.getenv('LLM_MODEL')
        
        if not self.api_key:
            print("Error: Missing LLM_API_KEY in .env.agent.secret", file=sys.stderr)
            print("Please set up your LLM API key first.", file=sys.stderr)
            sys.exit(1)
        
        self.project_root = Path.cwd()
        self.tools = Tools(self.project_root)
        self.tool_calls_history = []
    
    def _get_tool_definitions(self) -> List[Dict[str, Any]]:
        """
        Define read_file and list_files as tool schemas.
        
        Returns OpenAI-compatible tool definitions for both tools.
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read a file from the project repository to get documentation content",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Relative path from project root (e.g., 'wiki/git-workflow.md')"
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
                    "description": "List files and directories at a given path to discover available documentation",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Relative directory path from project root (default: '.')",
                                "default": "."
                            }
                        }
                    }
                }
            }
        ]
    
    def _get_system_prompt(self) -> str:
        """
        System prompt that guides the LLM to use tools correctly and include source.
        """
        return """You are a documentation agent for the SE Toolkit project.
You have access to two tools:
- list_files(path): List files in a directory (use to discover available wiki files)
- read_file(path): Read a file's contents (use to find answers)

Your task: Answer questions by reading the wiki files.

IMPORTANT INSTRUCTIONS:
1. FIRST, use list_files("wiki") to see what documentation files are available
2. THEN, use read_file on relevant files to find the answer
3. WHEN YOU FIND THE ANSWER, include the source reference on a separate line:
   Source: path/to/file.md#section-name
4. The source MUST point to the specific file and section where you found the information

Example:
Answer: To resolve a merge conflict, edit the file and remove conflict markers.
Source: wiki/git-workflow.md#resolving-merge-conflicts

The wiki directory contains documentation files. Start by listing it."""
    
    async def _call_llm(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Call the LLM API with messages and tool definitions."""
        url = f"{self.api_base.rstrip('/')}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "http://localhost:42002",
            "X-Title": "SE Toolkit Documentation Agent"
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
        lines = content.split('\n')
        for line in lines:
            if line.lower().startswith('source:'):
                return line[7:].strip()
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
    
    async def ask(self, question: str) -> Dict[str, Any]:
        """
        Process a question using the agentic loop.
        
        Args:
            question: The user's question
            
        Returns:
            Dictionary with answer, source, and tool_calls
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
            
            # Add assistant message to history
            messages.append(message)
            
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
                
                # Continue the loop (go back to LLM with tool results)
                continue
            
            # No tool calls - extract answer and source
            if 'content' in message and message['content']:
                content = message['content']
                
                answer = self._extract_answer(content)
                source = self._extract_source(content)
                
                print(f"\nFinal answer extracted with source: {source}", file=sys.stderr)
                
                # Return JSON with answer, source, and tool_calls
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
        agent = DocumentationAgent()
        result = await agent.ask(question)
        
        # Output JSON to stdout
        print(json.dumps(result, ensure_ascii=False))
        
    except Exception as e:
        print(f"\nError: {str(e)}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())