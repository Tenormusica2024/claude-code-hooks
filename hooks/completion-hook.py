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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hook_utils import (  # noqa: E402
    extract_assistant_message,
    scan_transcript_tool_outputs,
    split_clauses,
    strip_ansi,
)


TRIGGER_TOOLS = {"Edit", "Write", "MultiEdit"}
TRIGGER_THRESHOLD = 5

_COMPLETION_PATTERNS = [
    re.compile(r"完了(?:した|です|しました)?"),
    re.compile(r"できたよ"),
    re.compile(r"できた"),
    re.compile(r"実装した"),
    re.compile(r"修正した"),
    re.compile(r"追記した"),
    re.compile(r"追加した"),
    re.compile(r"更新した"),
    re.compile(r"対応した"),
    re.compile(r"終わった"),
    re.compile(r"完成した"),
    # 「完成」単体は「未完成」「完成度」「完成形」等にも誤マッチするため除外
    re.compile(r"\bdone\b", re.IGNORECASE),
    re.compile(r"\bfinished\b", re.IGNORECASE),
    re.compile(r"\bimplemented\b", re.IGNORECASE),
    re.compile(r"\bfixed\b", re.IGNORECASE),
    re.compile(r"\bupdated\b", re.IGNORECASE),
]

# 「完了している理由」「完了後に」等の文法的・説明的な用法をvetoする
_GRAMMAR_VETO_PATTERNS = [
    re.compile(r"完了(?:している|した)?(?:理由|ため|ので|から|条件|時|後|前|判定|状態|フラグ|イベント|通知)"),
    re.compile(r"完了を(?:確認|検知|チェック|待機|待つ)"),
    re.compile(r"(?:完了|done|finished)\s+(?:reason|because|since|when|after|before|if)", re.IGNORECASE),
]

# 説明的な文脈（「〜のため」「because」等）を含む節は完了宣言から除外する
_EXPLANATORY_PATTERNS = [
    re.compile(r"(?:理由|ため|ので|から)"),
    re.compile(r"\b(?:because|since|when|after|before|if)\b", re.IGNORECASE),
]

_EXCLUSION_PATTERNS = [
    re.compile(r"細かい"),
    re.compile(r"軽微"),
    re.compile(r"typo", re.IGNORECASE),
    re.compile(r"1行"),
    re.compile(r"コメント"),
    re.compile(r"ドキュメント"),
    re.compile(r"README", re.IGNORECASE),
    # テスト関連ワードは除外しない: 「テストを実装完了した」等の正当な完了宣言を誤減点しないため
    re.compile(r"確認済み"),
    re.compile(r"テスト済み"),
    re.compile(r"\bpass(?:ed)?\b", re.IGNORECASE),
    re.compile(r"通った"),
    re.compile(r"グリーン"),
]


def _contains_completion_signal(clause: str) -> bool:
    for pattern in _COMPLETION_PATTERNS:
        if pattern.search(clause):
            return True
    return False


def _contains_grammar_veto(clause: str) -> bool:
    for pattern in _GRAMMAR_VETO_PATTERNS:
        if pattern.search(clause):
            return True
    return False


def _is_explanatory_completion_clause(clause: str) -> bool:
    """完了シグナルはあるが説明的用法（〜のため等）を含む節か判定する。"""
    if not _contains_completion_signal(clause):
        return False
    for pattern in _EXPLANATORY_PATTERNS:
        if pattern.search(clause):
            return True
    return False


def _has_exclusion_pattern(text: str) -> bool:
    for pattern in _EXCLUSION_PATTERNS:
        if pattern.search(text):
            return True
    return False


def score_completion_turn(hook_input: dict, transcript_path: str) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []

    scan = scan_transcript_tool_outputs(transcript_path)
    has_mutation_tool = bool(scan.get("has_mutation_tool"))
    tool_names_used = scan.get("tool_names_used", [])
    last_tool_name = tool_names_used[-1] if tool_names_used else ""

    # Edit/Write/MultiEdit の有無が最重要証拠
    if has_mutation_tool:
        score += 5
        reasons.append("+5 mutation tool used in current turn")
    else:
        score -= 5
        reasons.append("-5 no mutation tool used in current turn")

    # 最後に使ったツールがmutationならさらに加点
    if last_tool_name in TRIGGER_TOOLS:
        score += 3
        reasons.append("+3 last used tool is mutation tool")

    assistant_message = strip_ansi(extract_assistant_message(hook_input))
    clauses = split_clauses(assistant_message)

    # 文法vetoパターンが全体に含まれていれば大きく減点
    if any(_contains_grammar_veto(clause) for clause in clauses):
        score -= 6
        reasons.append("-6 grammar veto pattern detected")

    # 除外パターン（typo/コメント/テスト関連等）
    if _has_exclusion_pattern(assistant_message):
        score -= 4
        reasons.append("-4 exclusion pattern detected")

    # 節単位で強い完了シグナルを確認
    has_strong_completion = False
    for clause in clauses:
        if not _contains_completion_signal(clause):
            continue
        if _contains_grammar_veto(clause):
            continue
        if _is_explanatory_completion_clause(clause):
            continue
        has_strong_completion = True
        break

    if has_strong_completion:
        score += 4
        reasons.append("+4 strong completion clause detected")

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

    # transcript_path がない場合はコンテキスト判定不能なのでスキップ
    transcript_path = hook_input.get("transcript_path", "")
    if not isinstance(transcript_path, str) or not transcript_path:
        sys.exit(0)

    score, reasons = score_completion_turn(hook_input, transcript_path)

    if score < TRIGGER_THRESHOLD:
        sys.exit(0)

    reason = (
        "[COMPLETION GATE BLOCKED] You reported task completion without running tests/verification.\n"
        "Quality gate:\n"
        "  RUN TESTS if: significant implementation, new feature, bug fix, multi-file change\n"
        "  SKIP if: typo fix, comment change, single-line trivial edit, documentation only\n"
        "If RUN TESTS: run appropriate tests (pytest/npm test/curl/screenshot) based on project context. Do NOT ask the user.\n"
        "If SKIP: silently continue.\n"
        f"[score={score}, reasons={reasons}]"
    )
    json.dump({"decision": "block", "reason": reason}, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
