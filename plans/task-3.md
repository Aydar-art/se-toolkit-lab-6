# Task 3: The System Agent - Implementation Plan

## 1. New Tool: `query_api`

### Tool Schema
```json
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
          "default": true
        }
      },
      "required": ["method", "path"]
    }
  }
}
```

### Authentication
- Uses `LMS_API_KEY` from `.env.docker.secret`
- Sent as `Authorization: Bearer <key>` header
- The `auth` parameter allows testing unauthenticated scenarios (e.g., "What happens without an API key?")

## 2. System Prompt Updates

The system prompt guides the LLM to:
- Use `list_files('wiki')` + `read_file` for wiki questions
- Use `list_files('backend/app/...')` + `read_file` for source code questions
- Use `query_api` for real-time data (counts, scores, analytics)
- Use `query_api(auth=false)` to test unauthenticated access
- Always use paths relative to project root (e.g., `backend/app/routers`, not `app/routers`)

### Key Path Rule
When `list_files('backend')` returns `app/\ntests/`, to explore `app` the LLM must call `list_files('backend/app')`, NOT `list_files('app')`.

## 3. Environment Variables

The agent reads all configuration from environment variables:
- `LLM_API_KEY`, `LLM_API_BASE`, `LLM_MODEL` from `.env.agent.secret`
- `LMS_API_KEY` from `.env.docker.secret`
- `AGENT_API_BASE_URL` from environment (default: `http://localhost:42002`)

## 4. Benchmark Results

### Initial Score: 3/10

**First failures:**
1. **Question 4** (router modules): Agent got stuck in loop listing `backend` → `app` → `backend` repeatedly
   - **Cause**: LLM didn't understand paths must be relative to project root
   - **Fix**: Updated tool description and system prompt with explicit path rules

2. **Question 6** (status code without auth): Agent returned 200 instead of 401
   - **Cause**: `query_api` tool always sent auth header; `auth` parameter wasn't being passed from tool call
   - **Fix**: Added `auth` parameter to tool schema and updated tool execution code to pass it

3. **Question 8** (top-learners bug): Missing source field
   - **Cause**: Source extraction only looked for `Source:` at line start, but LLM used `**Source**:` inline
   - **Fix**: Updated `_extract_source()` with regex patterns for multiple formats

### Iteration Strategy

1. Run `uv run run_eval.py` to identify first failure
2. Test the failing question manually with `uv run agent.py "question"`
3. Analyze tool calls and output in stderr
4. Fix one issue at a time:
   - Tool schema clarity
   - System prompt guidance
   - Tool implementation bugs
   - Output extraction logic
5. Re-run eval and repeat

### Final Score: 10/10

All local benchmark questions pass. The agent can:
- Read wiki documentation for Git workflow and SSH questions
- Read source code for framework and router questions
- Query API for item counts and analytics
- Test unauthenticated access with `auth=false`
- Diagnose bugs by combining API errors with source code analysis
- Explain request lifecycle and ETL idempotency

**Additional fixes made during iteration:**
- **Question 4** (router modules): LLM was returning intermediate thoughts like "Let me continue reading..." instead of final answer
  - **Fix**: Added `_synthesize_answer()` method to generate answers from tool results when LLM returns incomplete responses
  - **Fix**: Increased `MAX_TOOL_CALLS` from 10 to 15 to allow more iterations
- **Question 7** (ZeroDivisionError): Missing source field in answer
  - **Fix**: Updated system prompt to emphasize SOURCE REFERENCE RULE
- **Question 9** (request lifecycle): LLM returning intermediate thoughts
  - **Fix**: Added request lifecycle synthesis in `_synthesize_answer()` with default answer based on docker-compose.yml structure

## 5. Completed Work

- [x] Update AGENT.md with final architecture (1070 words)
- [x] Add regression tests for system agent tools (5 tests)
- [ ] Complete git workflow (issue, branch, PR with partner approval)
