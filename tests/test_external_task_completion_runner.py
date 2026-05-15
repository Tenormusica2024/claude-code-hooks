# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


RUNNER = Path(__file__).parent.parent / "hooks" / "external-task-completion-runner.py"


def write_task(tmp_path: Path, body: str) -> Path:
    script = tmp_path / "task.py"
    script.write_text(body, encoding="utf-8")
    return script


def run_runner(task_script: Path, *runner_args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(RUNNER), "--gate-json", *runner_args, "--", sys.executable, str(task_script)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def report_json(*, ok: bool = True, dry_run: bool = False, returncode: int = 0) -> str:
    return json.dumps(
        {
            "ok": ok,
            "schema_version": 1,
            "repo_root": "C:\\repo",
            "live_test_pane": "lower_right",
            "steps": [
                {
                    "name": "pytest",
                    "command": ["python", "-m", "pytest", "-q", "test_pane_auto_v2_preflight_runner.py"],
                    "returncode": returncode,
                    "dry_run": dry_run,
                }
            ],
            "dry_run": dry_run,
        },
        ensure_ascii=False,
    )


def test_runner_invokes_gate_only_after_task_exits(tmp_path: Path):
    task = write_task(
        tmp_path,
        "import sys\n"
        "print('task-start')\n"
        f"print({report_json()!r})\n"
        "print('task-stderr', file=sys.stderr)\n",
    )
    result = run_runner(task)
    assert result.returncode == 0
    assert "task-start" in result.stdout
    assert '"decision": "pass"' in result.stdout
    assert "task-stderr" in result.stderr


def test_runner_blocks_dry_run_by_default(tmp_path: Path):
    task = write_task(tmp_path, f"print({report_json(dry_run=True)!r})\n")
    result = run_runner(task)
    assert result.returncode == 1
    assert '"decision": "block"' in result.stdout
    assert "dry-run preflight" in result.stdout


def test_runner_allows_dry_run_when_requested(tmp_path: Path):
    task = write_task(tmp_path, f"print({report_json(dry_run=True)!r})\n")
    result = run_runner(task, "--allow-dry-run")
    assert result.returncode == 0
    assert '"decision": "pass"' in result.stdout


def test_runner_fails_when_task_outputs_no_report(tmp_path: Path):
    task = write_task(tmp_path, "print('no json report')\n")
    result = run_runner(task)
    assert result.returncode == 1
    assert '"decision": "block"' in result.stdout
    assert "no_report" in result.stdout


def test_runner_preserves_external_command_failure_even_if_report_passes(tmp_path: Path):
    task = write_task(tmp_path, f"print({report_json()!r})\nraise SystemExit(7)\n")
    result = run_runner(task)
    assert result.returncode == 7
    assert '"decision": "pass"' in result.stdout

