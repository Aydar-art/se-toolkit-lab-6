"""Tests for the system agent with API query tool."""

import subprocess
import json
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_system_framework_question():
    """
    Test that agent uses read_file to find framework information.
    """
    print("\n=== Running test_system_framework_question ===", file=sys.stderr)

    # Get project root directory
    project_root = Path(__file__).parent.parent

    # Run the agent
    result = subprocess.run(
        [sys.executable, "agent.py", "What Python web framework does this project's backend use? Read the source code to find out."],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=project_root
    )

    print(f"Exit code: {result.returncode}", file=sys.stderr)
    if result.returncode != 0:
        print(f"Stderr: {result.stderr}", file=sys.stderr)

    assert result.returncode == 0

    try:
        output = json.loads(result.stdout)
        print(f"Parsed JSON: {json.dumps(output, indent=2)}", file=sys.stderr)
    except json.JSONDecodeError as e:
        print(f"Raw stdout: {result.stdout}", file=sys.stderr)
        assert False, f"Output is not valid JSON: {e}"

    # Check required fields
    assert "answer" in output
    assert "tool_calls" in output

    # Should have used read_file
    tool_names = [t["tool"] for t in output["tool_calls"]]
    assert "read_file" in tool_names, f"Should use read_file, used: {tool_names}"

    # Answer should mention FastAPI
    answer_lower = output["answer"].lower()
    assert "fastapi" in answer_lower, f"Answer should mention FastAPI, got: {output['answer']}"

    print("✓ test_system_framework_question passed", file=sys.stderr)


def test_data_query_question():
    """
    Test that agent uses query_api for data questions.
    """
    print("\n=== Running test_data_query_question ===", file=sys.stderr)

    project_root = Path(__file__).parent.parent

    # Run the agent
    result = subprocess.run(
        [sys.executable, "agent.py", "How many items are currently stored in the database? Query the running API to find out."],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=project_root
    )

    print(f"Exit code: {result.returncode}", file=sys.stderr)

    assert result.returncode == 0

    try:
        output = json.loads(result.stdout)
        print(f"Parsed JSON: {json.dumps(output, indent=2)}", file=sys.stderr)
    except json.JSONDecodeError as e:
        print(f"Raw stdout: {result.stdout}", file=sys.stderr)
        assert False, f"Output is not valid JSON: {e}"

    # Check required fields
    assert "answer" in output
    assert "tool_calls" in output

    # Should have used query_api
    tool_names = [t["tool"] for t in output["tool_calls"]]
    assert "query_api" in tool_names, f"Should use query_api, used: {tool_names}"

    # Answer should contain a number
    import re
    assert re.search(r'\d+', output["answer"]), f"Answer should contain a number, got: {output['answer']}"

    print("✓ test_data_query_question passed", file=sys.stderr)


def test_api_status_code_question():
    """
    Test that agent uses query_api for status code questions.
    """
    print("\n=== Running test_api_status_code_question ===", file=sys.stderr)

    project_root = Path(__file__).parent.parent

    result = subprocess.run(
        [sys.executable, "agent.py", "What HTTP status code does the API return when you request /items/ without an authentication header?"],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=project_root
    )

    assert result.returncode == 0

    try:
        output = json.loads(result.stdout)
    except json.JSONDecodeError:
        assert False, "Output is not valid JSON"

    tool_names = [t["tool"] for t in output["tool_calls"]]
    assert "query_api" in tool_names

    # Answer should mention 401 or 403
    answer_lower = output["answer"].lower()
    assert "401" in answer_lower or "403" in answer_lower or "unauthorized" in answer_lower

    print("✓ test_api_status_code_question passed", file=sys.stderr)


def test_router_discovery_question():
    """
    Test that agent uses list_files to discover router modules.
    """
    print("\n=== Running test_router_discovery_question ===", file=sys.stderr)

    project_root = Path(__file__).parent.parent

    result = subprocess.run(
        [sys.executable, "agent.py", "List all API router modules in the backend. What domain does each one handle?"],
        capture_output=True,
        text=True,
        timeout=90,
        cwd=project_root
    )

    assert result.returncode == 0

    try:
        output = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        assert False, f"Output is not valid JSON: {e}"

    assert "answer" in output
    assert "tool_calls" in output

    # Should have used list_files
    tool_names = [t["tool"] for t in output["tool_calls"]]
    assert "list_files" in tool_names, f"Should use list_files, used: {tool_names}"

    # Answer should mention multiple routers
    answer_lower = output["answer"].lower()
    assert "analytics" in answer_lower or "items" in answer_lower, f"Answer should mention router domains, got: {output['answer']}"

    print("✓ test_router_discovery_question passed", file=sys.stderr)


def test_bug_diagnosis_question():
    """
    Test that agent uses query_api + read_file to diagnose bugs.
    """
    print("\n=== Running test_bug_diagnosis_question ===", file=sys.stderr)

    project_root = Path(__file__).parent.parent

    result = subprocess.run(
        [sys.executable, "agent.py", "Query the /analytics/completion-rate endpoint for a lab that has no data (e.g., lab-99). What error do you get, and what is the bug in the source code?"],
        capture_output=True,
        text=True,
        timeout=90,
        cwd=project_root
    )

    assert result.returncode == 0

    try:
        output = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        assert False, f"Output is not valid JSON: {e}"

    assert "answer" in output
    assert "tool_calls" in output

    # Should have used both query_api and read_file
    tool_names = [t["tool"] for t in output["tool_calls"]]
    assert "query_api" in tool_names, f"Should use query_api, used: {tool_names}"
    assert "read_file" in tool_names, f"Should use read_file, used: {tool_names}"

    # Answer should mention ZeroDivisionError or division by zero
    answer_lower = output["answer"].lower()
    assert "zerodivision" in answer_lower or "division" in answer_lower, f"Answer should mention division error, got: {output['answer']}"

    print("✓ test_bug_diagnosis_question passed", file=sys.stderr)


if __name__ == "__main__":
    """Run tests manually."""
    test_system_framework_question()
    test_data_query_question()
    test_api_status_code_question()
    test_router_discovery_question()
    test_bug_diagnosis_question()
    print("\n✓ All tests passed!", file=sys.stderr)