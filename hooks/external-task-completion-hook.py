# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import io
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

if sys.platform == "win32":
    sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


PANE_AUTO_V2_PREFLIGHT_MARKERS = (
    "pane_auto_v2_preflight.py",
    "pane-auto-v2-preflight",
    "pane_auto_v2_preflight",
)


@dataclass
class GateResult:
    decision: str
    reason: str
    source: str = "external_task_completion"
    blockers: list[str] = field(default_factory=list)
    advisories: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def blocked(self) -> bool:
        return self.decision == "block"

    def to_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "decision": self.decision,
            "reason": self.reason,
            "source": self.source,
        }
        if self.blockers:
            payload["blockers"] = self.blockers
        if self.advisories:
            payload["advisories"] = self.advisories
        if self.evidence:
            payload["evidence"] = self.evidence
        return payload


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return " ".join(_as_text(item) for item in value if item is not None)
    if isinstance(value, dict):
        pieces: list[str] = []
        for key in ("stdout", "stderr", "output", "text", "content", "message"):
            if key in value:
                pieces.append(_as_text(value.get(key)))
        if pieces:
            return "\n".join(piece for piece in pieces if piece)
    return str(value)


def _load_payload(path: str | None) -> dict[str, Any] | None:
    try:
        raw = Path(path).read_text(encoding="utf-8", errors="replace") if path else sys.stdin.read()
    except OSError:
        return None
    if not raw.strip():
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {"_raw_text": raw}
    return payload if isinstance(payload, dict) else {"_raw_json": payload}


def _extract_command(payload: dict[str, Any]) -> str:
    for container_key in ("tool_input", "input", "parameters", "tool_call", "request"):
        container = payload.get(container_key)
        if isinstance(container, dict):
            for key in ("command", "cmd", "args", "argv"):
                if key in container:
                    return _as_text(container.get(key))
    for key in ("command", "cmd", "args", "argv"):
        if key in payload:
            return _as_text(payload.get(key))
    return ""


def _extract_tool_output(payload: dict[str, Any]) -> str:
    pieces: list[str] = []
    for key in (
        "tool_response",
        "tool_output",
        "response",
        "result",
        "output",
        "completed",
        "observation",
    ):
        if key in payload:
            text = _as_text(payload.get(key))
            if text:
                pieces.append(text)
    for key in ("stdout", "stderr", "_raw_text"):
        text = _as_text(payload.get(key))
        if text:
            pieces.append(text)
    return "\n".join(pieces)


def _command_matches_profile(command: str, profile: str) -> bool:
    if profile != "pane-auto-v2-preflight":
        return True
    lowered = command.lower()
    return any(marker in lowered for marker in PANE_AUTO_V2_PREFLIGHT_MARKERS)


def _decode_json_object_from_text(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if not stripped:
        return None
    try:
        parsed = json.loads(stripped)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for match in re.finditer(r"{", text):
        candidate = text[match.start() :]
        try:
            parsed, _end = decoder.raw_decode(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _looks_like_preflight_report(payload: dict[str, Any]) -> bool:
    return isinstance(payload.get("steps"), list) and ("ok" in payload or "schema_version" in payload)


def _extract_report(payload: dict[str, Any], *, profile: str, always_evaluate: bool) -> tuple[dict[str, Any] | None, str]:
    if _looks_like_preflight_report(payload):
        return payload, "direct_report"

    command = _extract_command(payload)
    if command and not always_evaluate and not _command_matches_profile(command, profile):
        return None, "unrelated_tool"

    output_text = _extract_tool_output(payload)
    report = _decode_json_object_from_text(output_text)
    if report and _looks_like_preflight_report(report):
        return report, "tool_output_report"
    return None, "no_report"


def _step_name(step: dict[str, Any]) -> str:
    return str(step.get("name") or step.get("tool_name") or step.get("id") or "unnamed_step")


def _step_command(step: dict[str, Any]) -> str:
    return _as_text(step.get("command") or step.get("cmd") or step.get("args") or step.get("argv"))


def _step_returncode(step: dict[str, Any]) -> int | None:
    value = step.get("returncode", step.get("exit_code", step.get("code")))
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _has_test_step(steps: list[dict[str, Any]]) -> bool:
    for step in steps:
        haystack = f"{_step_name(step)} {_step_command(step)}".lower()
        if "pytest" in haystack or re.search(r"\b(test|tests)\b", haystack):
            return True
    return False


def _git_status(repo_root: Path) -> tuple[bool, str]:
    try:
        completed = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"git status failed: {exc}"
    if completed.returncode != 0:
        return False, (completed.stderr or completed.stdout or "git status failed").strip()
    output = completed.stdout.strip()
    return not bool(output), output


def _git_ahead_count(repo_root: Path) -> tuple[bool, str]:
    try:
        upstream = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"git upstream check failed: {exc}"
    if upstream.returncode != 0:
        return False, "git upstream is not configured"

    try:
        counts = subprocess.run(
            ["git", "rev-list", "--left-right", "--count", "@{u}...HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"git ahead check failed: {exc}"
    if counts.returncode != 0:
        return False, (counts.stderr or counts.stdout or "git ahead check failed").strip()
    parts = counts.stdout.strip().split()
    if len(parts) != 2:
        return False, f"unexpected git ahead output: {counts.stdout.strip()}"
    ahead = int(parts[1])
    return ahead == 0, str(ahead)


def _has_doc_evidence(report: dict[str, Any]) -> bool:
    evidence = report.get("evidence")
    if isinstance(evidence, dict):
        for key in ("docs_updated", "documentation_updated", "doc_updated"):
            if evidence.get(key):
                return True
    changed_files = report.get("changed_files") or report.get("changedFiles") or []
    if isinstance(changed_files, str):
        changed_files = [changed_files]
    if isinstance(changed_files, list):
        for path in changed_files:
            lowered = str(path).lower()
            if lowered.endswith((".md", ".mdx", ".rst")) or "/docs/" in lowered or "\\docs\\" in lowered:
                return True
    return False


def evaluate_preflight_report(
    report: dict[str, Any],
    *,
    allow_dry_run: bool,
    require_clean_git: bool,
    require_pushed: bool,
    require_doc_evidence: bool,
    require_test_step: bool,
) -> GateResult:
    blockers: list[str] = []
    advisories: list[str] = []
    steps = [step for step in report.get("steps", []) if isinstance(step, dict)]
    failed_steps = []
    for step in steps:
        returncode = _step_returncode(step)
        if returncode is not None and returncode != 0:
            failed_steps.append(f"{_step_name(step)} returncode={returncode}")

    if report.get("ok") is not True:
        blockers.append("preflight report ok is not true")
    if failed_steps:
        blockers.append("failed step(s): " + ", ".join(failed_steps))
    if not steps:
        blockers.append("preflight report has no steps")
    if not allow_dry_run and (report.get("dry_run") or any(step.get("dry_run") for step in steps)):
        blockers.append("dry-run preflight cannot close a final completion gate")
    if require_test_step and not _has_test_step(steps):
        blockers.append("no test-like step evidence found in preflight steps")

    repo_root_text = str(report.get("repo_root") or "").strip()
    repo_root = Path(repo_root_text) if repo_root_text else None
    if require_clean_git:
        if not repo_root:
            blockers.append("require_clean_git enabled but repo_root is missing")
        else:
            clean, detail = _git_status(repo_root)
            if not clean:
                blockers.append(f"git worktree is not clean: {detail[:500]}")
    if require_pushed:
        if not repo_root:
            blockers.append("require_pushed enabled but repo_root is missing")
        else:
            pushed, detail = _git_ahead_count(repo_root)
            if not pushed:
                blockers.append(f"git branch has unpushed commits or no upstream: {detail[:500]}")
    if require_doc_evidence and not _has_doc_evidence(report):
        blockers.append("documentation evidence is required but no doc update evidence was found")

    manual_checks = report.get("manual_only_checks")
    if isinstance(manual_checks, list) and manual_checks:
        advisories.append("manual/live-operation handoff remains after preflight: " + "; ".join(map(str, manual_checks[:3])))
    handoff = report.get("recommended_live_test_handoff")
    if isinstance(handoff, dict) and handoff.get("success_criteria"):
        advisories.append("recommended_live_test_handoff is present; treat preflight PASS as handoff boundary, not final production proof")

    evidence = {
        "ok": report.get("ok"),
        "step_count": len(steps),
        "failed_step_count": len(failed_steps),
        "dry_run": bool(report.get("dry_run") or any(step.get("dry_run") for step in steps)),
        "has_test_step": _has_test_step(steps),
        "repo_root": repo_root_text,
    }

    if blockers:
        return GateResult(
            decision="block",
            reason="[EXTERNAL TASK COMPLETION GATE BLOCKED] " + " / ".join(blockers),
            source="pane_auto_v2_preflight" if report.get("live_test_pane") else "external_task_completion",
            blockers=blockers,
            advisories=advisories,
            evidence=evidence,
        )
    return GateResult(
        decision="pass",
        reason="[EXTERNAL TASK COMPLETION GATE PASSED] preflight task evidence is sufficient",
        source="pane_auto_v2_preflight" if report.get("live_test_pane") else "external_task_completion",
        advisories=advisories,
        evidence=evidence,
    )


def evaluate_payload(args: argparse.Namespace) -> GateResult:
    payload = _load_payload(args.input)
    if payload is None:
        return GateResult(decision="noop", reason="empty input")

    report, state = _extract_report(payload, profile=args.profile, always_evaluate=args.always_evaluate)
    if report is None:
        if state == "unrelated_tool":
            return GateResult(decision="noop", reason="tool command is unrelated to selected profile")
        if args.profile == "pane-auto-v2-preflight":
            return GateResult(decision="noop", reason="no pane auto v2 preflight JSON report found")
        return GateResult(decision="block", reason="no external task completion report found", blockers=["no_report"])

    return evaluate_preflight_report(
        report,
        allow_dry_run=args.allow_dry_run,
        require_clean_git=args.require_clean_git,
        require_pushed=args.require_pushed,
        require_doc_evidence=args.require_doc_evidence,
        require_test_step=not args.no_require_test_step,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gate external tool task completion events such as Pane Auto v2 preflight")
    parser.add_argument("--input", help="Read hook/event JSON from this file instead of stdin")
    parser.add_argument("--profile", default="pane-auto-v2-preflight", choices=["pane-auto-v2-preflight", "generic"])
    parser.add_argument("--always-evaluate", action="store_true", help="Evaluate input even when a PostToolUse command does not match the profile marker")
    parser.add_argument("--allow-dry-run", action="store_true", help="Allow dry-run reports to pass")
    parser.add_argument("--no-require-test-step", action="store_true", help="Do not require test-like step evidence")
    parser.add_argument("--require-clean-git", action="store_true", help="Block if repo_root has uncommitted or untracked changes")
    parser.add_argument("--require-pushed", action="store_true", help="Block if repo_root has commits ahead of upstream")
    parser.add_argument("--require-doc-evidence", action="store_true", help="Block unless report has documentation update evidence")
    parser.add_argument("--json", action="store_true", help="Print pass/noop results too; block results are always printed")
    parser.add_argument("--strict-exit", action="store_true", help="Exit 1 when the gate blocks")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = evaluate_payload(args)
    if result.blocked or args.json:
        json.dump(result.to_json(), sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    if result.blocked and args.strict_exit:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
