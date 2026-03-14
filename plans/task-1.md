# Task 1: Call an LLM from Code - Implementation Plan

## LLM Provider Choice
I will use **Qwen Code API** running on my VM because:
- 1000 free requests per day
- Works from Russia without VPN
- No credit card required
- Strong tool calling support (needed for later tasks)

## Model
- `qwen3-coder-plus` - recommended model with strong coding capabilities

## Environment Configuration
- Create `.env.agent.secret` from `.env.agent.example`
- Set `LLM_API_KEY`, `LLM_API_BASE`, `LLM_MODEL`

## Agent Structure
1. Read environment variables from `.env.agent.secret`
2. Get question from command line argument
3. Prepare OpenAI-compatible API request
4. Send request to LLM with timeout
5. Parse response and extract answer
6. Output JSON with required fields
7. All debug output goes to stderr

## Implementation Details
- Use `httpx` for async HTTP requests
- Use `python-dotenv` for loading environment variables
- Implement error handling with appropriate exit codes
- Add timeout of 60 seconds

## Testing Strategy
- Create one regression test that runs agent as subprocess
- Test with sample question and verify JSON output structure
- Test error cases (no question, API failure, timeout)