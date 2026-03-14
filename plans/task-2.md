# Task 2: The Documentation Agent - Implementation Plan

## Overview
Add tool-calling capabilities to the agent from Task 1, enabling it to read files and list directories from the project wiki.

## Tool Definitions

### 1. `read_file`
- **Purpose**: Read contents of a file from the project
- **Parameters**: `path` (string) - relative path from project root
- **Security**: Validate path to prevent directory traversal (no `..` or absolute paths)
- **Returns**: File contents or error message

### 2. `list_files`
- **Purpose**: List files and directories at a given path
- **Parameters**: `path` (string) - relative directory path
- **Security**: Same path validation as read_file
- **Returns**: Newline-separated listing

## Agentic Loop Implementation
