## Tool Calling Capabilities

The agent now supports **tool calling** - it can use tools to gather information before answering.

### Available Tools

#### 1. `read_file(path: string)`
Reads a file from the project repository.
- **Parameters**: `path` - relative path from project root
- **Returns**: File contents or error message
- **Security**: Validates paths to prevent directory traversal

#### 2. `list_files(path: string = ".")`
Lists files and directories at the specified path.
- **Parameters**: `path` - relative directory path (default: ".")
- **Returns**: Newline-separated listing with directories marked by "/"
- **Security**: Same path validation as read_file

### Agentic Loop

The agent now uses a proper agentic loop:

1. Send question + tool definitions to LLM
2. If LLM requests tool calls:
   - Execute each tool
   - Add results as new messages
   - Repeat (max 10 iterations)
3. If LLM provides final answer:
   - Extract answer and source
   - Output JSON with full history

### System Prompt Strategy

The system prompt guides the agent to:
1. First explore available files using `list_files`
2. Then read relevant files using `read_file`
3. Find the answer and its source location
4. Provide answer with source reference

### Output Format

```json
{
  "answer": "Edit the conflicting file, choose which changes to keep, then stage and commit.",
  "source": "wiki/git-workflow.md#resolving-merge-conflicts",
  "tool_calls": [
    {
      "tool": "list_files",
      "args": {"path": "wiki"},
      "result": "git-workflow.md\ntesting.md\n"
    },
    {
      "tool": "read_file",
      "args": {"path": "wiki/git-workflow.md"},
      "result": "# Git Workflow\n\n## Resolving merge conflicts...\n"
    }
  ]
}
