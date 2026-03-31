# -*- coding: utf-8 -*-
from __future__ import annotations

import io
import json
import re
import sys

if sys.platform == "win32":
    sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


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
    (re.compile(r"完了だよ"), "完了だよ"),
    (re.compile(r"完了♪"), "完了♪"),
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


def load_transcript(path: str) -> list[dict]:
    """transcript_path を JSON / JSONL どちらの形式でも読み込む。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
    except OSError:
        return []

    # JSON 配列として試みる
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("messages", [])
    except (json.JSONDecodeError, ValueError):
        pass

    # JSONL として試みる
    messages: list[dict] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                messages.append(obj)
        except (json.JSONDecodeError, ValueError):
            pass
    return messages


def had_file_edits_in_current_turn(transcript_path: str) -> bool:
    """直前のユーザー入力以降、Edit/Write/MultiEdit が呼ばれたか確認する。

    チャットだけの返答（ツール未使用）は完了ゲートの対象外にするための判定。
    """
    messages = load_transcript(transcript_path)
    if not messages:
        return False

    # 最後の「本物のユーザーメッセージ」（tool_result ではない）のインデックスを探す
    last_user_idx = -1
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        if not isinstance(msg, dict) or msg.get("role") != "user":
            continue
        content = msg.get("content", "")
        # tool_result のみで構成されている user メッセージはスキップ
        if isinstance(content, list):
            if all(
                isinstance(b, dict) and b.get("type") == "tool_result"
                for b in content
                if isinstance(b, dict)
            ):
                continue
        last_user_idx = i
        break

    if last_user_idx == -1:
        return False

    # last_user_idx より後のアシスタントメッセージに TRIGGER_TOOLS が含まれるか確認
    for msg in messages[last_user_idx + 1 :]:
        if not isinstance(msg, dict) or msg.get("role") != "assistant":
            continue
        content = msg.get("content", [])
        if not isinstance(content, list):
            continue
        for block in content:
            if (
                isinstance(block, dict)
                and block.get("type") == "tool_use"
                and block.get("name", "") in TRIGGER_TOOLS
            ):
                return True

    return False


def extract_text_from_content(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                if block.get("type") == "text":
                    text = block.get("text")
                    if isinstance(text, str):
                        parts.append(text)
                elif isinstance(block.get("content"), str):
                    parts.append(block["content"])
        return "\n".join(part for part in parts if part)
    if isinstance(content, dict):
        text = content.get("text")
        if isinstance(text, str):
            return text
    return ""


def extract_assistant_message(hook_input: dict) -> str:
    value = hook_input.get("last_assistant_message")
    if isinstance(value, str) and value:
        return value

    for key in ("assistant_message", "message", "content", "output"):
        value = hook_input.get(key)
        if isinstance(value, str) and value:
            return value

    transcript_path = hook_input.get("transcript_path")
    if not isinstance(transcript_path, str) or not transcript_path:
        return ""

    messages = load_transcript(transcript_path)
    for item in reversed(messages):
        if isinstance(item, dict) and item.get("role") == "assistant":
            return extract_text_from_content(item.get("content"))

    return ""


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

    # ファイル編集ツールが使われていない場合はチャット返答なのでスキップ
    transcript_path = hook_input.get("transcript_path", "")
    if isinstance(transcript_path, str) and transcript_path:
        if not had_file_edits_in_current_turn(transcript_path):
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
