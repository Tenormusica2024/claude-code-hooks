# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


HOOK = Path(__file__).parent.parent / "hooks" / "external-task-completion-hook.py"


def run_hook(payload: dict, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HOOK), "--json", *args],
        input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        capture_output=True,
    )


def parse_stdout(result: subprocess.CompletedProcess) -> dict:
    text = result.stdout.decode("utf-8").strip()
    assert text, result.stderr.decode("utf-8", errors="replace")
    return json.loads(text)


def successful_preflight_report() -> dict:
    return {
        "ok": True,
        "schema_version": 1,
        "repo_root": "C:\\repo",
        "live_test_pane": "lower_right",
        "steps": [
            {
                "name": "pytest",
                "command": ["python", "-m", "pytest", "-q", "test_pane_auto_v2_preflight_runner.py"],
                "returncode": 0,
                "dry_run": False,
                "stdout": "1 passed",
                "stderr": "",
            }
        ],
        "dry_run": False,
    }


def test_direct_successful_preflight_passes():
    result = run_hook(successful_preflight_report())
    payload = parse_stdout(result)
    assert result.returncode == 0
    assert payload["decision"] == "pass"
    assert payload["evidence"]["has_test_step"] is True


def test_dry_run_preflight_blocks_by_default():
    report = successful_preflight_report()
    report["dry_run"] = True
    report["steps"][0]["dry_run"] = True
    result = run_hook(report, "--strict-exit")
    payload = parse_stdout(result)
    assert result.returncode == 1
    assert payload["decision"] == "block"
    assert "dry-run" in payload["reason"]


def test_posttooluse_unrelated_command_noops():
    hook_input = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "python other_script.py"},
        "tool_response": {"stdout": json.dumps(successful_preflight_report(), ensure_ascii=False)},
    }
    result = run_hook(hook_input)
    payload = parse_stdout(result)
    assert result.returncode == 0
    assert payload["decision"] == "noop"


def test_posttooluse_preflight_command_parses_prefixed_stdout_and_blocks_failure():
    report = successful_preflight_report()
    report["ok"] = False
    report["steps"][0]["returncode"] = 1
    hook_input = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "python .\\pane_auto_v2_preflight.py --changed-file visible_pane_send.py"},
        "tool_response": {
            "stdout": "running preflight...\n" + json.dumps(report, ensure_ascii=False, indent=2) + "\nfinished\n"
        },
    }
    result = run_hook(hook_input, "--strict-exit")
    payload = parse_stdout(result)
    assert result.returncode == 1
    assert payload["decision"] == "block"
    assert "returncode=1" in payload["reason"]


def test_posttooluse_preflight_command_ignores_unrelated_json_before_report():
    report = successful_preflight_report()
    hook_input = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "python .\\pane_auto_v2_preflight.py"},
        "tool_response": {
            "stdout": json.dumps({"progress": "starting"}, ensure_ascii=False)
            + "\n"
            + json.dumps(report, ensure_ascii=False)
        },
    }
    result = run_hook(hook_input)
    payload = parse_stdout(result)
    assert result.returncode == 0
    assert payload["decision"] == "pass"


def test_posttooluse_preflight_command_blocks_when_report_missing():
    hook_input = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "python .\\pane_auto_v2_preflight.py"},
        "tool_response": {"stdout": "preflight started but JSON was truncated"},
    }
    result = run_hook(hook_input, "--strict-exit")
    payload = parse_stdout(result)
    assert result.returncode == 1
    assert payload["decision"] == "block"
    assert payload["blockers"] == ["profile_command_no_report"]


def test_require_report_blocks_empty_direct_wrapper_input():
    result = subprocess.run(
        [sys.executable, str(HOOK), "--json", "--strict-exit", "--require-report"],
        input=b"",
        capture_output=True,
    )
    payload = parse_stdout(result)
    assert result.returncode == 1
    assert payload["decision"] == "block"
    assert payload["blockers"] == ["empty_input"]


def test_require_report_blocks_unparseable_direct_wrapper_output():
    result = run_hook({"_raw_text": "preflight crashed before JSON"}, "--strict-exit", "--require-report")
    payload = parse_stdout(result)
    assert result.returncode == 1
    assert payload["decision"] == "block"
    assert payload["blockers"] == ["no_report"]


def test_missing_test_step_blocks():
    report = successful_preflight_report()
    report["steps"][0]["name"] = "lint"
    report["steps"][0]["command"] = ["python", "-m", "ruff", "check", "."]
    result = run_hook(report, "--strict-exit")
    payload = parse_stdout(result)
    assert result.returncode == 1
    assert payload["decision"] == "block"
    assert "no test-like step" in payload["reason"]


def test_missing_returncode_blocks():
    report = successful_preflight_report()
    del report["steps"][0]["returncode"]
    result = run_hook(report, "--strict-exit")
    payload = parse_stdout(result)
    assert result.returncode == 1
    assert payload["decision"] == "block"
    assert "missing returncode" in payload["reason"]
