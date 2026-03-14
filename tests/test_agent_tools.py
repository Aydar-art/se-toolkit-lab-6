"""Tests for the documentation agent with tool calling."""

import subprocess
import json
import sys
import os
from pathlib import Path

# Add parent directory to path so we can import agent if needed
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_list_files_tool():
    """
    Test that agent uses list_files to discover wiki files.
    """
    print("\n=== Running test_list_files_tool ===", file=sys.stderr)
    
    # Ensure wiki directory exists with test files
    wiki_dir = Path("wiki")
    wiki_dir.mkdir(exist_ok=True)
    
    # Create test files if they don't exist
    git_workflow = wiki_dir / "git-workflow.md"
    if not git_workflow.exists():
        git_workflow.write_text("""# Git Workflow

## Resolving merge conflicts
When you have a merge conflict:
1. Edit the conflicting files
2. Remove conflict markers
3. Stage and commit
""")
    
    testing = wiki_dir / "testing.md"
    if not testing.exists():
        testing.write_text("""# Testing Guide

## Running tests
Use `uv run pytest` to run tests.
""")
    
    # Run the agent
    result = subprocess.run(
        [sys.executable, "agent.py", "What files are in the wiki directory?"],
        capture_output=True,
        text=True,
        timeout=60
    )
    
    # Print debug info
    print(f"Exit code: {result.returncode}", file=sys.stderr)
    print(f"STDERR: {result.stderr}", file=sys.stderr)
    
    # Check exit code
    assert result.returncode == 0, f"Agent failed with code {result.returncode}"
    
    # Parse JSON output
    try:
        output = json.loads(result.stdout)
        print(f"Parsed JSON: {json.dumps(output, indent=2)}", file=sys.stderr)
    except json.JSONDecodeError as e:
        print(f"Raw stdout: {result.stdout}", file=sys.stderr)
        assert False, f"Output is not valid JSON: {e}"
    
    # Check required fields
    assert "answer" in output, "Missing 'answer' field"
    assert "source" in output, "Missing 'source' field"
    assert "tool_calls" in output, "Missing 'tool_calls' field"
    
    # Check that tool_calls is populated
    assert len(output["tool_calls"]) > 0, "tool_calls should not be empty"
    
    # Check that list_files was used
    tool_names = [t["tool"] for t in output["tool_calls"]]
    assert "list_files" in tool_names, f"Agent should use list_files tool, used: {tool_names}"
    
    print("✓ test_list_files_tool passed", file=sys.stderr)


def test_read_file_tool():
    """
    Test that agent uses read_file to find specific information.
    """
    print("\n=== Running test_read_file_tool ===", file=sys.stderr)
    
    # Ensure git-workflow.md exists with merge conflict info
    wiki_dir = Path("wiki")
    wiki_dir.mkdir(exist_ok=True)
    
    git_workflow = wiki_dir / "git-workflow.md"
    git_workflow.write_text("""# Git Workflow

## Resolving merge conflicts
When you have a merge conflict:
1. Edit the conflicting files to resolve differences
2. Remove the conflict markers (<<<<<<<, =======, >>>>>>>)
3. Stage the resolved files: `git add <file>`
4. Complete the merge: `git commit`
""")
    
    # Run the agent
    result = subprocess.run(
        [sys.executable, "agent.py", "How do you resolve a merge conflict?"],
        capture_output=True,
        text=True,
        timeout=60
    )
    
    print(f"Exit code: {result.returncode}", file=sys.stderr)
    print(f"STDERR: {result.stderr}", file=sys.stderr)
    
    assert result.returncode == 0
    
    try:
        output = json.loads(result.stdout)
        print(f"Parsed JSON: {json.dumps(output, indent=2)}", file=sys.stderr)
    except json.JSONDecodeError as e:
        print(f"Raw stdout: {result.stdout}", file=sys.stderr)
        assert False, f"Output is not valid JSON: {e}"
    
    # Check required fields
    assert "answer" in output
    assert "source" in output
    assert "tool_calls" in output
    
    # tool_calls is populated
    assert len(output["tool_calls"]) > 0
    
    # read_file was used
    tool_names = [t["tool"] for t in output["tool_calls"]]
    assert "read_file" in tool_names, f"Agent should use read_file tool, used: {tool_names}"
    
    print("✓ test_read_file_tool passed", file=sys.stderr)


def test_tool_calls_structure():
    """
    Test that tool_calls entries have correct structure.
    """
    print("\n=== Running test_tool_calls_structure ===", file=sys.stderr)
    
    result = subprocess.run(
        [sys.executable, "agent.py", "What is in the wiki about testing?"],
        capture_output=True,
        text=True,
        timeout=60
    )
    
    assert result.returncode == 0
    
    try:
        output = json.loads(result.stdout)
    except json.JSONDecodeError:
        print(f"Stdout: {result.stdout}", file=sys.stderr)
        assert False, "Output is not valid JSON"
    
    # Check structure of each tool call
    for tc in output["tool_calls"]:
        assert "tool" in tc
        assert isinstance(tc["tool"], str)
        
        assert "args" in tc
        assert isinstance(tc["args"], dict)
        
        assert "result" in tc
        assert isinstance(tc["result"], str)
    
    print("✓ test_tool_calls_structure passed", file=sys.stderr)


if __name__ == "__main__":
    """Run tests manually."""
    test_list_files_tool()
    test_read_file_tool()
    test_tool_calls_structure()
    print("\n✓ All tests passed!", file=sys.stderr)