# -*- coding: utf-8 -*-
from __future__ import annotations

import io
import json
import os
import re
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hook_utils import (  # noqa: E402
    detect_test_command_in_output,
    detect_test_framework_output,
    extract_assistant_message,
    scan_transcript_tool_outputs,
    split_clauses,
    strip_ansi,
)


TRIGGER_THRESHOLD = 6
PENDING_ISSUES_PATH = Path.home() / ".claude" / "hooks" / "pending_issues.json"

# テストの説明・議論文脈を検出してスコアを下げるパターン
_TEST_EXPLANATION_PATTERNS = [
    re.compile(r"テストについて説明"),
    re.compile(r"テストの目的"),
    re.compile(r"テスト方針"),
    re.compile(r"テスト観点"),
    re.compile(r"テストケース"),
    re.compile(r"テスト手順"),
    re.compile(r"test explanation", re.IGNORECASE),
    re.compile(r"about tests?", re.IGNORECASE),
]

# テスト成功を示すアシスタントメッセージ内の表現
_TEST_SUCCESS_PATTERNS = [
    re.compile(r"通った"),
    re.compile(r"成功"),
    re.compile(r"グリーン"),
    re.compile(r"\bpassed\b", re.IGNORECASE),
    re.compile(r"\ball passed\b", re.IGNORECASE),
    re.compile(r"\btests passed\b", re.IGNORECASE),
    re.compile(r"All tests passed", re.IGNORECASE),
    re.compile(r"パス"),
]

# 「パス」がファイルパスの意味で使われていると判定するパターン
_PATH_CONTEXT_PATTERNS = [
    re.compile(r"[\\/]"),
    re.compile(r"\.(?:py|js|ts|tsx|jsx|json|yaml|yml|toml|ini|md)\b", re.IGNORECASE),
    re.compile(r"ファイルパス"),
    re.compile(r"フォルダパス"),
    re.compile(r"パス名"),
    re.compile(r"パスを"),
    re.compile(r"パスの"),
    re.compile(r"パスは"),
    re.compile(r"\bPATH\b"),
    re.compile(r"\bimport\s+\S+", re.IGNORECASE),
    re.compile(r"\brequire\s*\(", re.IGNORECASE),
]

_FAILURE_PATTERNS = [
    re.compile(r"\bFAILED\b", re.IGNORECASE),
    re.compile(r"\bFAIL\b(?!\w)", re.IGNORECASE),
    re.compile(r"\bAssertionError\b", re.IGNORECASE),
    re.compile(r"\bError:", re.IGNORECASE),
    re.compile(r"\bTraceback\b", re.IGNORECASE),
    re.compile(r"\b0 passed\b", re.IGNORECASE),
    re.compile(r"\b[1-9]\d*\s+failed\b", re.IGNORECASE),
    re.compile(r"\b[1-9]\d*\s+failures?\b", re.IGNORECASE),
]


def contains_unresolved_entries(data: object) -> bool:
    if isinstance(data, dict):
        if data.get("resolved") is False:
            return True
        return any(contains_unresolved_entries(value) for value in data.values())
    if isinstance(data, list):
        return any(contains_unresolved_entries(item) for item in data)
    return False


def has_pending_issues() -> bool:
    if not PENDING_ISSUES_PATH.exists() or not PENDING_ISSUES_PATH.is_file():
        return False
    try:
        with open(PENDING_ISSUES_PATH, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError, ValueError):
        return False
    return contains_unresolved_entries(payload)


def _contains_failure_output(text: str) -> bool:
    cleaned = strip_ansi(text)
    if not cleaned:
        return False
    for pattern in _FAILURE_PATTERNS:
        if pattern.search(cleaned):
            return True
    return False


def _is_path_context_for_pass(clause: str) -> bool:
    """「パス」がファイルパスの意味で使われているか判定する。"""
    if "パス" not in clause and "pass" not in clause.lower():
        return False
    for pattern in _PATH_CONTEXT_PATTERNS:
        if pattern.search(clause):
            return True
    return False


def _is_test_explanation_clause(clause: str) -> bool:
    """テストの説明・議論文脈（「テストについて説明」等）か判定する。"""
    cleaned = clause.strip()
    if not cleaned:
        return False
    for pattern in _TEST_EXPLANATION_PATTERNS:
        if pattern.search(cleaned):
            return True
    # 「test/テスト + 説明/目的/概要/とは」の組み合わせを検出
    if re.search(r"\btest\b", cleaned, re.IGNORECASE) and re.search(r"(説明|目的|概要|とは)", cleaned):
        return True
    if "テスト" in cleaned and re.search(r"(説明|目的|概要|とは)", cleaned):
        return True
    return False


def _clause_has_test_success(clause: str) -> bool:
    """節がテスト成功を示しているか判定する（パス文脈・説明文脈は除外）。"""
    cleaned = strip_ansi(clause)
    if not cleaned:
        return False
    if _is_path_context_for_pass(cleaned):
        return False
    if _is_test_explanation_clause(cleaned):
        return False
    for pattern in _TEST_SUCCESS_PATTERNS:
        if pattern.search(cleaned):
            return True
    return False


def score_test_complete_turn(hook_input: dict, transcript_path: str) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []

    scan = scan_transcript_tool_outputs(transcript_path)
    bash_outputs = scan.get("bash_outputs", [])
    all_outputs = scan.get("all_outputs", [])

    combined_bash_text = "\n".join(strip_ansi(text) for text in bash_outputs if text)
    combined_all_text = "\n".join(strip_ansi(text) for text in all_outputs if text)

    # Bash出力にテストフレームワークの典型的な成功出力を検出（最強証拠）
    if any(detect_test_framework_output(text) for text in bash_outputs):
        score += 6
        reasons.append("+6 test framework output detected in bash outputs")

    # Bash出力にテストコマンド実行の痕跡を検出
    if detect_test_command_in_output(combined_bash_text):
        score += 4
        reasons.append("+4 test command evidence detected in bash output")

    # MCP系テストツール（playwright/puppeteer等）の使用
    if bool(scan.get("has_mcp_test_tool")):
        score += 3
        reasons.append("+3 MCP test tool used")

    # Bashツール自体の使用（弱証拠。テスト無関係な Bash でも加点されるため +1 に抑制）
    if bool(scan.get("has_bash")):
        score += 1
        reasons.append("+1 Bash tool used")

    # ツール出力に失敗パターンがあれば大きく減点
    if _contains_failure_output(combined_all_text):
        score -= 5
        reasons.append("-5 failure pattern detected in tool output")

    assistant_message = strip_ansi(extract_assistant_message(hook_input))
    clauses = split_clauses(assistant_message)

    # アシスタントメッセージの節でテスト成功を報告しているか
    if any(_clause_has_test_success(clause) for clause in clauses):
        score += 3
        reasons.append("+3 assistant reported test success")

    # 「パス」がファイルパス文脈で使われていたら減点
    if any(_is_path_context_for_pass(clause) for clause in clauses):
        score -= 4
        reasons.append("-4 pass/path context detected in assistant message")

    # テスト説明文脈（「テストについて説明」等）なら減点
    if any(_is_test_explanation_clause(clause) for clause in clauses):
        score -= 3
        reasons.append("-3 explanatory test context detected")

    return score, reasons


def main() -> None:
    try:
        raw_input = sys.stdin.read()
        if not raw_input.strip():
            sys.exit(0)
        hook_input = json.loads(raw_input)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    if hook_input.get("stop_hook_active"):
        sys.exit(0)

    if has_pending_issues():
        sys.exit(0)

    # transcript_path がない場合はコンテキスト判定不能なのでスキップ
    transcript_path = hook_input.get("transcript_path", "")
    if not isinstance(transcript_path, str) or not transcript_path:
        sys.exit(0)

    score, reasons = score_test_complete_turn(hook_input, transcript_path)

    if score < TRIGGER_THRESHOLD:
        sys.exit(0)

    reason = (
        "[TEST COMPLETE GATE] Tests passed. Now run the full review pipeline.\n"
        "Execute: /ifr --d\n"
        "This triggers dual-agent review (Opus + Codex). If already in a review context, skip.\n"
        f"[score={score}, reasons={reasons}]"
    )
    json.dump({"decision": "block", "reason": reason}, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
