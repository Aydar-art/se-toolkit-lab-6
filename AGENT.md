# Agent Documentation

## Overview
`agent.py` is a simple CLI program that sends questions to an LLM and returns structured JSON responses. It serves as the foundation for building more complex agents with tool calling capabilities.

## Architecture

### Components
1. **Environment Configuration**: Uses `.env.agent.secret` for LLM credentials
2. **LLMAgent Class**: Handles API communication and response parsing
3. **Async HTTP Client**: Uses `httpx` for non-blocking requests
4. **JSON Output**: Always returns valid JSON with required fields

### Data Flow