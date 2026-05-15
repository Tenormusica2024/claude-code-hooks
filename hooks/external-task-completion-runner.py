# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import io
import subprocess
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


DEFAULT_GATE_SCRIPT = Path(__file__).resolve().with_name("external-task-completion-hook.py")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run an external task and invoke external-task-completion-hook only "
            "after the task process exits."
        )
    )
    parser.add_argument("--cwd", help="Working directory for the external command")
    parser.add_argument("--gate-script", default=str(DEFAULT_GATE_SCRIPT), help="Path to external-task-completion-hook.py")
    parser.add_argument("--profile", default="pane-auto-v2-preflight", choices=["pane-auto-v2-preflight", "generic"])
    parser.add_argument("--allow-dry-run", action="store_true", help="Forward --allow-dry-run to the gate")
    parser.add_argument("--no-require-test-step", action="store_true", help="Forward --no-require-test-step to the gate")
    parser.add_argument("--require-clean-git", action="store_true", help="Forward --require-clean-git to the gate")
    parser.add_argument("--require-pushed", action="store_true", help="Forward --require-pushed to the gate")
    parser.add_argument("--require-doc-evidence", action="store_true", help="Forward --require-doc-evidence to the gate")
    parser.add_argument("--gate-json", action="store_true", help="Print gate JSON for pass/noop as well as block")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="Command to run after --")
    return parser.parse_args()


def normalize_command(command: list[str]) -> list[str]:
    if command and command[0] == "--":
        return command[1:]
    return command


def build_gate_command(args: argparse.Namespace) -> list[str]:
    command = [
        sys.executable,
        str(Path(args.gate_script)),
        "--profile",
        args.profile,
        "--require-report",
        "--strict-exit",
    ]
    if args.allow_dry_run:
        command.append("--allow-dry-run")
    if args.no_require_test_step:
        command.append("--no-require-test-step")
    if args.require_clean_git:
        command.append("--require-clean-git")
    if args.require_pushed:
        command.append("--require-pushed")
    if args.require_doc_evidence:
        command.append("--require-doc-evidence")
    if args.gate_json:
        command.append("--json")
    return command


def _write_streams(stdout: str, stderr: str) -> None:
    if stdout:
        sys.stdout.write(stdout)
        if not stdout.endswith("\n"):
            sys.stdout.write("\n")
    if stderr:
        sys.stderr.write(stderr)
        if not stderr.endswith("\n"):
            sys.stderr.write("\n")


def run_external_command(command: list[str], cwd: str | None) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def run_gate(gate_command: list[str], report_text: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        gate_command,
        input=report_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def main() -> int:
    args = parse_args()
    external_command = normalize_command(args.command)
    if not external_command:
        sys.stderr.write("external-task-completion-runner requires a command after --\n")
        return 2

    task = run_external_command(external_command, cwd=args.cwd)
    _write_streams(task.stdout or "", task.stderr or "")

    gate = run_gate(build_gate_command(args), task.stdout or "")
    _write_streams(gate.stdout or "", gate.stderr or "")

    if task.returncode != 0:
        return task.returncode
    if gate.returncode != 0:
        return gate.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
