# -*- coding: utf-8 -*-
from __future__ import annotations

import io
import json
import os
import re
import sys

if sys.platform == "win32":
    sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# 同じディレクトリの hook_utils を参照する
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hook_utils import extract_assistant_message, had_tools_in_current_turn  # noqa: E402


CONTEXT_WINDOW = 120

# ファイル編集系のツール呼び出しがあった場合のみ完了ゲートを発動する
TRIGGER_TOOLS = {"Edit", "Write", "MultiEdit"}

COMPLETION_PATTERNS = [
    (re.compile(r"完了"), "完了"),
    (re.compile(r"できたよ"), "できたよ"),
    (re.compile(r"できた"), "できた"),
    (re.compile(r"実装した"), "実装した"),
    (re.compile(r"修正した"), "修正した"),
    (re.compile(r"追記した"), "追記した"),
    (re.compile(r"追加した"), "追加した"),
    (re.compile(r"更新した"), "更新した"),
    (re.compile(r"対応した"), "対応した"),
    (re.compile(r"終わった"), "終わった"),
    (re.compile(r"完成した"), "完成した"),
    (re.compile(r"完成"), "完成"),
    (re.compile(r"したよ"), "したよ"),
    (re.compile(r"したね"), "したね"),
    (re.compile(r"\bdone\b", re.IGNORECASE), "done"),
    (re.compile(r"\bfinished\b", re.IGNORECASE), "finished"),
]

EXCLUSION_PATTERNS = [
    re.compile(r"細かい", re.IGNORECASE),
    re.compile(r"軽微", re.IGNORECASE),
    re.compile(r"typo", re.IGNORECASE),
    re.compile(r"1行", re.IGNORECASE),
    re.compile(r"コメント", re.IGNORECASE),
    re.compile(r"ドキュメント", re.IGNORECASE),
    re.compile(r"README", re.IGNORECASE),
    re.compile(r"テスト", re.IGNORECASE),
    re.compile(r"\btest\b", re.IGNORECASE),
    re.compile(r"\bspec\b", re.IGNORECASE),
    re.compile(r"確認済み", re.IGNORECASE),
    re.compile(r"テスト済み", re.IGNORECASE),
    re.compile(r"\bpass(?:ed)?\b", re.IGNORECASE),
    re.compile(r"通った", re.IGNORECASE),
    re.compile(r"グリーン", re.IGNORECASE),
]


def get_surrounding_context(text: str, start: int, end: int, window: int = CONTEXT_WINDOW) -> str:
    ctx_start = max(0, start - window)
    ctx_end = min(len(text), end + window)
    return text[ctx_start:ctx_end]


def is_excluded(context: str) -> bool:
    return any(pattern.search(context) for pattern in EXCLUSION_PATTERNS)


def detect_completion_claims(text: str) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []

    for pattern, label in COMPLETION_PATTERNS:
        for match in pattern.finditer(text):
            context = get_surrounding_context(text, match.start(), match.end())
            if is_excluded(context):
                continue
            findings.append(
                {
                    "pattern": label,
                    "matched": match.group(),
                    "context": context.strip(),
                }
            )

    return findings


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

    # transcript_path がない場合はコンテキスト判定不能なのでスキップ
    transcript_path = hook_input.get("transcript_path", "")
    if not isinstance(transcript_path, str) or not transcript_path:
        sys.exit(0)

    # ファイル編集ツールが使われていない場合はチャット返答なのでスキップ
    if not had_tools_in_current_turn(transcript_path, TRIGGER_TOOLS):
        sys.exit(0)

    assistant_message = extract_assistant_message(hook_input)
    if not assistant_message:
        sys.exit(0)

    findings = detect_completion_claims(assistant_message)
    if not findings:
        sys.exit(0)

    reason = (
        "[COMPLETION GATE BLOCKED] You reported task completion without running tests/verification.\n"
        "Quality gate:\n"
        "  RUN TESTS if: significant implementation, new feature, bug fix, multi-file change\n"
        "  SKIP if: typo fix, comment change, single-line trivial edit, documentation only\n"
        "If RUN TESTS: run appropriate tests (pytest/npm test/curl/screenshot) based on project context. Do NOT ask the user.\n"
        "If SKIP: silently continue."
    )
    json.dump({"decision": "block", "reason": reason}, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
