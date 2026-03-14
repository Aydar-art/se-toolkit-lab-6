# Task 3: The System Agent - Implementation Plan

## 1. New Tool: `query_api`

### Tool Schema
```json
{
  "type": "function",
  "function": {
    "name": "query_api",
    "description": "Send HTTP requests to the deployed backend API to get real-time data",
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
        }
      },
      "required": ["method", "path"]
    }
  }
}