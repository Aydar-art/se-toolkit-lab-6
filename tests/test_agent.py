"""Regression tests for agent.py."""

import subprocess
import json
import sys
from pathlib import Path


def test_agent_basic_question():
    """Test that agent.py returns valid JSON with answer and tool_calls."""
    # Run the agent with a simple question
    result = subprocess.run(
        [sys.executable, "agent.py", "What is 2+2?"],
        capture_output=True,
        text=True,
        timeout=30
    )
    
    # Check exit code
    assert result.returncode == 0, f"Agent failed with exit code {result.returncode}"
    
    # Parse stdout as JSON
    try:
        output = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        print(f"Stdout: {result.stdout}", file=sys.stderr)
        print(f"Stderr: {result.stderr}", file=sys.stderr)
        assert False, f"Invalid JSON output: {e}"
    
    # Check required fields
    assert "answer" in output, "Missing 'answer' field"
    assert "tool_calls" in output, "Missing 'tool_calls' field"
    assert isinstance(output["tool_calls"], list), "'tool_calls' must be a list"
    assert len(output["tool_calls"]) == 0, "tool_calls should be empty for Task 1"
    
    # Answer should be non-empty
    assert output["answer"], "Answer should not be empty"


def test_agent_no_question():
    """Test that agent.py handles missing question gracefully."""
    result = subprocess.run(
        [sys.executable, "agent.py"],
        capture_output=True,
        text=True
    )
    
    # Should exit with error
    assert result.returncode != 0, "Should fail with no question"
    
    # Should have error message in stderr
    assert "No question provided" in result.stderr or "Usage" in result.stderr


def test_agent_json_format():
    """Test that output is always valid JSON with the correct structure."""
    result = subprocess.run(
        [sys.executable, "agent.py", "Say 'test'"],
        capture_output=True,
        text=True,
        timeout=30
    )
    
    assert result.returncode == 0
    
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        print(f"Invalid JSON: {result.stdout}", file=sys.stderr)
        assert False, "Output is not valid JSON"
    
    # Check structure
    assert isinstance(data, dict)
    assert "answer" in data
    assert isinstance(data["answer"], str)
    assert "tool_calls" in data
    assert isinstance(data["tool_calls"], list)