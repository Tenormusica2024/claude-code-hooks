# -*- coding: utf-8 -*-
"""completion-hook / test-complete-hook 共通ユーティリティ。"""
from __future__ import annotations

import json


def load_transcript(path: str) -> list[dict]:
    """transcript_path を JSON / JSONL どちらの形式でも読み込む。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
    except OSError:
        return []

    # JSON 配列 / dict として試みる
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


def had_tools_in_current_turn(transcript_path: str, trigger_tools: set[str]) -> bool:
    """直前のユーザー入力以降、指定したツールが呼ばれたか確認する。

    Args:
        transcript_path: Claude Code が渡す会話ログのファイルパス。
        trigger_tools: 検出対象のツール名集合（例: {"Edit", "Write", "MultiEdit"}）。

    Returns:
        trigger_tools のいずれかが呼ばれていれば True。
        transcript が読めない・ユーザー入力が見つからない場合は False。
    """
    messages = load_transcript(transcript_path)
    if not messages:
        return False

    # 最後の「本物のユーザーメッセージ」（tool_result のみで構成されていないもの）を探す
    last_user_idx = -1
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        if not isinstance(msg, dict) or msg.get("role") != "user":
            continue
        content = msg.get("content", "")
        # content が非空リストかつ全要素が tool_result の場合はスキップ
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

    # last_user_idx より後のアシスタントメッセージに trigger_tools が含まれるか確認
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
                and block.get("name", "") in trigger_tools
            ):
                return True

    return False


def extract_text_from_content(content: object) -> str:
    """Claude メッセージの content フィールドからテキストを抽出する。"""
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
    """フック入力から最後のアシスタントメッセージのテキストを取得する。

    優先順位:
    1. hook_input["last_assistant_message"]
    2. hook_input の他のテキストフィールド
    3. transcript_path のログから逆順スキャン
    """
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
