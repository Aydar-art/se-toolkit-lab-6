#!/usr/bin/env python3
"""
CLI agent that sends a question to an LLM and returns a JSON response.

Usage:
    uv run agent.py "Your question here"

Environment variables (from .env.agent.secret):
    LLM_API_KEY: API key for the LLM provider
    LLM_API_BASE: Base URL for the OpenAI-compatible API
    LLM_MODEL: Model name to use
"""

import os
import sys
import json
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any

import httpx
from dotenv import load_dotenv


# Load environment variables from .env.agent.secret
load_dotenv('.env.agent.secret')


class LLMAgent:
    """Simple agent that calls an LLM API and returns structured responses."""

    def __init__(self):
        """Initialize the agent with configuration from environment."""
        self.api_key = os.getenv('LLM_API_KEY')
        self.api_base = os.getenv('LLM_API_BASE')
        self.model = os.getenv('LLM_MODEL')
        
        # Validate required configuration
        if not all([self.api_key, self.api_base, self.model]):
            missing = []
            if not self.api_key:
                missing.append('LLM_API_KEY')
            if not self.api_base:
                missing.append('LLM_API_BASE')
            if not self.model:
                missing.append('LLM_MODEL')
            print(f"Error: Missing environment variables: {', '.join(missing)}", 
                  file=sys.stderr)
            sys.exit(1)
        
        # Debug output (to stderr)
        print(f"Initialized agent with model: {self.model}", file=sys.stderr)
        print(f"API Base: {self.api_base}", file=sys.stderr)

    async def ask(self, question: str) -> Dict[str, Any]:
        """
        Send a question to the LLM and get a response.
        
        Args:
            question: The user's question
            
        Returns:
            Dictionary with answer and tool_calls
        """
        # Prepare the request
        url = f"{self.api_base.rstrip('/')}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        # Simple system prompt for now
        system_prompt = "You are a helpful assistant. Answer the user's question concisely."
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question}
            ],
            "temperature": 0.7,
            "max_tokens": 500
        }
        
        print(f"Sending request to LLM...", file=sys.stderr)
        start_time = datetime.now()
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                
            elapsed = (datetime.now() - start_time).total_seconds()
            print(f"Response received in {elapsed:.2f} seconds", file=sys.stderr)
            
            # Extract the answer from the response
            if 'choices' in data and len(data['choices']) > 0:
                message = data['choices'][0]['message']
                answer = message.get('content', '')
                
                # For Task 1, tool_calls is always empty
                return {
                    "answer": answer.strip(),
                    "tool_calls": []
                }
            else:
                raise ValueError("Unexpected API response format")
                
        except httpx.TimeoutException:
            print("Error: Request timed out after 60 seconds", file=sys.stderr)
            return {
                "answer": "I'm sorry, the request timed out. Please try again.",
                "tool_calls": []
            }
        except httpx.HTTPStatusError as e:
            print(f"Error: HTTP {e.response.status_code} - {e.response.text}", 
                  file=sys.stderr)
            return {
                "answer": f"I'm sorry, I encountered an HTTP error: {e.response.status_code}",
                "tool_calls": []
            }
        except Exception as e:
            print(f"Error: {str(e)}", file=sys.stderr)
            return {
                "answer": "I'm sorry, an unexpected error occurred.",
                "tool_calls": []
            }


async def main():
    """Main entry point."""
    # Check command line arguments
    if len(sys.argv) < 2:
        print("Usage: uv run agent.py \"Your question here\"", file=sys.stderr)
        print("Error: No question provided", file=sys.stderr)
        sys.exit(1)
    
    question = sys.argv[1]
    
    # Debug output to stderr
    print(f"Question: {question}", file=sys.stderr)
    
    # Create agent and get answer
    agent = LLMAgent()
    result = await agent.ask(question)
    
    # Output JSON to stdout
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())