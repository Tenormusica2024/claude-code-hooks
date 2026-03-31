# -*- coding: utf-8 -*-
from __future__ import annotations

import io
import json
import re
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


CONTEXT_WINDOW = 120
PENDING_ISSUES_PATH = Path(r"C:\Users\Tenormusica\.claude\hooks\pending_issues.json")

# Bash が使われた場合のみテスト完了ゲートを発動する（説明文・会話での誤検知を防ぐ）
TRIGGER_TOOLS = {"Bash"}

TEST_PATTERNS = [
    re.compile(r"テスト", re.IGNORECASE),
    re.compile(r"\btest\b", re.IGNORECASE),
    re.compile(r"\bspec\b", re.IGNORECASE),
    re.compile(r"\bpytest\b", re.IGNORECASE),
    re.compile(r"\bjest\b", re.IGNORECASE),
    re.compile(r"\bcypress\b", re.IGNORECASE),
]

SUCCESS_PATTERNS = [
    re.compile(r"通った", re.IGNORECASE),
    re.compile(r"パス", re.IGNORECASE),
    re.compile(r"グリーン", re.IGNORECASE),
    re.compile(r"成功", re.IGNORECASE),
    re.compile(r"\bpassed\b", re.IGNORECASE),
    re.compile(r"(?<![A-Za-z])OK(?![A-Za-z])", re.IGNORECASE),  # 日本語混在でも検出
    re.compile(r"\ball passed\b", re.IGNORECASE),
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


def had_bash_in_current_turn(transcript_path: str) -> bool:
    """直前のユーザー入力以降、Bash が呼ばれたか確認する。

    Bash 未使用 = テストを実行していない会話ターンなので
    テスト完了ゲートの対象外にするための判定。
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
        if isinstance(content, list) and content:
            if all(
                isinstance(b, dict) and b.get("type") == "tool_result"
                for b in content
            ):
                continue
        last_user_idx = i
        break

    if last_user_idx == -1:
        return False

    # last_user_idx より後のアシスタントメッセージに Bash が含まれるか確認
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


def detect_test_success(text: str) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []

    for test_pattern in TEST_PATTERNS:
        for match in test_pattern.finditer(text):
            context = get_surrounding_context(text, match.start(), match.end())
            success_match = next(
                (p.search(context) for p in SUCCESS_PATTERNS if p.search(context)), None
            )
            if not success_match:
                continue
            findings.append(
                {
                    "test_word": match.group(),
                    "success_word": success_match.group(),
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

    if has_pending_issues():
        sys.exit(0)

    # Bash が使われていない場合はテスト未実行の会話ターンなのでスキップ
    transcript_path = hook_input.get("transcript_path", "")
    if isinstance(transcript_path, str) and transcript_path:
        if not had_bash_in_current_turn(transcript_path):
            sys.exit(0)

    assistant_message = extract_assistant_message(hook_input)
    if not assistant_message:
        sys.exit(0)

    findings = detect_test_success(assistant_message)
    if not findings:
        sys.exit(0)

    reason = (
        "[TEST COMPLETE GATE] Tests passed. Now run the full review pipeline.\n"
        "Execute: /ifr --d\n"
        "This triggers dual-agent review (Opus + Codex). If already in a review context, skip."
    )
    json.dump({"decision": "block", "reason": reason}, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
