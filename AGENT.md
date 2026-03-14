# System Agent Architecture (Task 3)

## Overview

This agent extends the Task 2 documentation agent with a new `query_api` tool that enables it to interact with the deployed backend API. The agent can now answer three types of questions:

1. **Wiki questions** - Read documentation files (e.g., Git workflow, SSH setup)
2. **Source code questions** - Read and analyze Python source files (e.g., framework, routers)
3. **System data questions** - Query the live API for real-time data (e.g., item counts, scores, analytics)

## Architecture

### Components

```
┌─────────────────────────────────────────────────────────────┐
│                      SystemAgent                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  Tools Class                                           │  │
│  │  ├── read_file(path) - Read files with security check  │  │
│  │  ├── list_files(path) - List directory contents        │  │
│  │  └── query_api(method, path, body, auth) - HTTP client │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  Agentic Loop                                          │  │
│  │  1. Send question + tools to LLM                       │  │
│  │  2. Execute tool calls (max 10 iterations)             │  │
│  │  3. Extract answer and source from final response      │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### Available Tools

#### 1. `read_file(path: string)`
Reads a file from the project repository.
- **Parameters**: `path` - relative path from project root (e.g., `backend/app/main.py`)
- **Returns**: File contents or error message
- **Security**: Validates paths to prevent directory traversal attacks

#### 2. `list_files(path: string = ".")`
Lists files and directories at the specified path.
- **Parameters**: `path` - relative directory path from project root (default: ".")
- **Returns**: Newline-separated listing with directories marked by "/"
- **Security**: Same path validation as read_file

#### 3. `query_api(method, path, body, auth)`
Sends HTTP requests to the deployed backend API.
- **Parameters**:
  - `method` - HTTP method (GET, POST, PUT, DELETE)
  - `path` - API endpoint (e.g., `/items/`, `/analytics/completion-rate?lab=lab-99`)
  - `body` - Optional JSON request body for POST/PUT
  - `auth` - Whether to include authentication header (default: true)
- **Returns**: JSON string with `status_code` and `body`
- **Authentication**: Uses `LMS_API_KEY` from environment as `Authorization: Bearer <key>`

### Environment Configuration

The agent reads all configuration from environment variables (not hardcoded):

| Variable | Purpose | Source |
|----------|---------|--------|
| `LLM_API_KEY` | LLM provider API key | `.env.agent.secret` |
| `LLM_API_BASE` | LLM API endpoint URL | `.env.agent.secret` |
| `LLM_MODEL` | Model name | `.env.agent.secret` |
| `LMS_API_KEY` | Backend API key for query_api | `.env.docker.secret` |
| `AGENT_API_BASE_URL` | Backend base URL (optional) | Environment, default: `http://localhost:42002` |

## System Prompt Strategy

The system prompt is critical for guiding the LLM to use the right tools. Key guidelines:

### Path Rules (Critical!)
Paths must ALWAYS be relative to the project root:
- ✅ Correct: `backend/app/routers`, `wiki/git-workflow.md`
- ❌ Wrong: `app/routers`, `git-workflow.md` (missing directory prefix)

When `list_files('backend')` returns `app/\ntests/`, to explore `app` the LLM must call `list_files('backend/app')`, NOT `list_files('app')`.

### Tool Selection Guidelines
- **Wiki questions** → `list_files('wiki')` + `read_file` on relevant docs
- **Source code questions** → `list_files('backend/app/...')` + `read_file` on source files
- **Data questions** (counts, scores) → `query_api` with GET method
- **Error diagnosis** → `query_api` first to see error, then `read_file` to find bug
- **Unauthenticated testing** → `query_api(auth=false)` to test behavior without API key

## Agentic Loop

```
1. Initialize messages with system prompt + user question
2. Loop (max 10 iterations):
   a. Call LLM with messages + tool definitions
   b. If LLM makes tool calls:
      - Execute each tool
      - Record in history
      - Add results as tool messages
      - Continue loop
   c. If LLM provides final answer:
      - Extract answer and source
      - Return JSON with tool_calls history
3. If max iterations reached without answer, return partial result
```

## Output Format

```json
{
  "answer": "The API returns HTTP 401 Unauthorized when requesting /items/ without authentication.",
  "source": "",
  "tool_calls": [
    {
      "tool": "query_api",
      "args": {"method": "GET", "path": "/items/", "auth": false},
      "result": "{\"status_code\": 401, \"body\": {\"detail\": \"Not authenticated\"}}"
    }
  ]
}
```

## Lessons Learned

### 1. Path Handling is Critical
The biggest challenge was teaching the LLM that paths must always be relative to the project root. The initial implementation had the agent stuck in loops: `list_files('backend')` → `list_files('app')` → error → `list_files('backend')` → repeat.

**Fix**: Added explicit path rules to both the tool description AND system prompt with concrete examples of correct vs. incorrect usage.

### 2. Tool Parameters Must Be Passed Correctly
When I added the `auth` parameter to `query_api`, I defined it in the schema but forgot to pass it in the tool execution code. The LLM was correctly calling `query_api(auth=false)`, but the Python code ignored it.

**Fix**: Updated the tool execution to extract and pass all parameters: `auth = arguments.get('auth', True)`.

### 3. Source Extraction Needs Flexibility
The LLM doesn't always format source references consistently. Sometimes `Source: path`, sometimes `**Source**: path`, sometimes inline at the end of a paragraph.

**Fix**: Used regex patterns to match multiple formats instead of simple line prefix matching.

### 4. Environment Variable Loading
The agent loads from `.env.agent.secret` for LLM credentials, but `LMS_API_KEY` is in `.env.docker.secret`. Initially only one file was loaded, causing authentication failures.

**Fix**: Load both files: `load_dotenv('.env.agent.secret')` and `load_dotenv('.env.docker.secret')`.

### 5. Debug Output Goes to stderr
All debug/logging output (agentic loop iterations, tool calls) goes to `sys.stderr` so that `stdout` contains only the JSON result. This allows clean parsing: `json.loads(subprocess_output)`.

## Benchmark Results

**Final Score: 10/10** on local evaluation

| # | Question Type | Tools Used | Status |
|---|---------------|------------|--------|
| 1 | Wiki: branch protection | `read_file` | ✅ |
| 2 | Wiki: SSH setup | `read_file` | ✅ |
| 3 | Source: framework | `read_file` | ✅ |
| 4 | Source: router modules | `list_files` | ✅ |
| 5 | Data: item count | `query_api` | ✅ |
| 6 | Auth: status without key | `query_api(auth=false)` | ✅ |
| 7 | Bug: ZeroDivisionError | `query_api`, `read_file` | ✅ |
| 8 | Bug: TypeError in sorting | `query_api`, `read_file` | ✅ |
| 9 | Reasoning: request lifecycle | `read_file` | ✅ |
| 10 | Reasoning: ETL idempotency | `read_file` | ✅ |

## Future Improvements

1. **Caching**: Cache frequently read files to reduce redundant tool calls
2. **Parallel execution**: Execute independent tool calls in parallel
3. **Better error messages**: Include more context in tool error responses
4. **Timeout handling**: Add per-tool timeouts to prevent hanging
5. **Tool discovery**: Allow the agent to dynamically discover available tools
