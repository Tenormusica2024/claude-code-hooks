# -*- coding: utf-8 -*-
"""completion-hook / test-complete-hook / document-update-detector / global-claude-md-appender 共通ユーティリティ。"""
from __future__ import annotations

import io
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path


# ---------------------------------------------------------------------------
# I/O・ファイルユーティリティ（document-update-detector / global-claude-md-appender 共用）
# ---------------------------------------------------------------------------

def configure_stdio() -> None:
    """Windows 環境で stdin/stdout/stderr を UTF-8 に設定する。"""
    if sys.platform == "win32":
        sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def log_error(message: str) -> None:
    print(message, file=sys.stderr)


def load_payload() -> dict[str, object] | None:
    """stdin から JSON ペイロードを読み込む。失敗時は None を返す。"""
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return None
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            log_error("Hook input must be a JSON object.")
            return None
        return payload
    except Exception as exc:
        log_error(f"Failed to parse hook input JSON: {exc}")
        return None


def backup_target_file(target_file: Path) -> Path | None:
    """タイムスタンプ付きバックアップを作成する。失敗時は None を返す。"""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup_path = target_file.with_name(f"{target_file.name}.{timestamp}.bak").resolve(strict=False)
    try:
        shutil.copy2(target_file, backup_path)
        return backup_path
    except Exception as exc:
        log_error(f"Failed to create backup for {target_file}: {exc}")
        return None


def ensure_history_dir(history_path: Path) -> None:
    """履歴ファイルの親ディレクトリを作成する。"""
    history_path.parent.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# テストフレームワーク検出ユーティリティ（completion-hook / test-complete-hook 共用）
# ---------------------------------------------------------------------------


_MUTATION_TOOL_NAMES = {"Edit", "Write", "MultiEdit"}
_MCP_TEST_TOOL_KEYWORDS = (
    "playwright",
    "puppeteer",
    "browser",
    "e2e",
    "cypress",
)

_ANSI_RE = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
# 半角ピリオドは「後ろが空白or行末」の場合のみ分割（v1.2.3 やファイルパス等の誤分割を防ぐ）
_CLAUSE_SPLIT_RE = re.compile(r"[。!？！\n]+|(?:\s*[、]\s*)|\.(?=\s|$)")


def strip_ansi(text: str) -> str:
    """ANSI エスケープコードや簡易制御コードを除去する。"""
    if not isinstance(text, str) or not text:
        return ""
    cleaned = _ANSI_RE.sub("", text)
    cleaned = cleaned.replace("\r", "\n")
    return cleaned


def split_clauses(text: str) -> list[str]:
    """句点・改行・!?・読点で節に分割する。"""
    if not isinstance(text, str) or not text:
        return []
    parts = _CLAUSE_SPLIT_RE.split(text)
    return [part.strip() for part in parts if part and part.strip()]


def load_transcript(path: str) -> list[dict]:
    """transcript_path を JSON / JSONL どちらの形式でも読み込む。"""
    if not isinstance(path, str) or not path:
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
    except OSError:
        return []

    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            messages = data.get("messages", [])
            if isinstance(messages, list):
                return [item for item in messages if isinstance(item, dict)]
    except (json.JSONDecodeError, ValueError, TypeError):
        pass

    messages: list[dict] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, ValueError, TypeError):
            continue
        if isinstance(obj, dict):
            messages.append(obj)
    return messages


def _is_tool_result_only_user_message(message: dict) -> bool:
    if not isinstance(message, dict) or message.get("role") != "user":
        return False
    content = message.get("content")
    if not isinstance(content, list) or not content:
        return False
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "tool_result":
            return False
    return True


def _find_last_real_user_index(messages: list[dict]) -> int:
    for i in range(len(messages) - 1, -1, -1):
        message = messages[i]
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        if _is_tool_result_only_user_message(message):
            continue
        return i
    return -1


def extract_text_from_content(content: object) -> str:
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
                continue
            if not isinstance(block, dict):
                continue

            block_type = block.get("type")
            if block_type == "text":
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
                continue

            nested = block.get("content")
            if isinstance(nested, str):
                parts.append(nested)
            elif isinstance(nested, list):
                nested_text = extract_text_from_content(nested)
                if nested_text:
                    parts.append(nested_text)

        return "\n".join(part for part in parts if part)

    if isinstance(content, dict):
        text = content.get("text")
        if isinstance(text, str):
            return text
        nested = content.get("content")
        if isinstance(nested, (str, list, dict)):
            return extract_text_from_content(nested)

    return ""


def _extract_tool_result_text(block: dict) -> str:
    if not isinstance(block, dict):
        return ""
    return extract_text_from_content(block.get("content"))


def _get_tool_result_id(block: dict) -> str:
    if not isinstance(block, dict):
        return ""
    for key in ("tool_use_id", "toolUseId", "id"):
        value = block.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def scan_transcript_tool_outputs(transcript_path: str) -> dict:
    """
    直近ユーザー入力以降の tool_result を収集する。

    Returns:
        {
          "bash_outputs": list[str],
          "all_outputs": list[str],
          "tool_names_used": list[str],
          "has_bash": bool,
          "has_mutation_tool": bool,
          "has_mcp_test_tool": bool,
        }
    """
    result: dict = {
        "bash_outputs": [],
        "all_outputs": [],
        "tool_names_used": [],
        "has_bash": False,
        "has_mutation_tool": False,
        "has_mcp_test_tool": False,
    }

    messages = load_transcript(transcript_path)
    if not messages:
        return result

    last_user_idx = _find_last_real_user_index(messages)
    if last_user_idx == -1:
        return result

    tool_name_by_id: dict[str, str] = {}
    tool_names_used: list[str] = []
    known_tool_names: set[str] = set()

    for message in messages[last_user_idx + 1:]:
        if not isinstance(message, dict):
            continue

        role = message.get("role")
        content = message.get("content")

        # アシスタントメッセージから tool_use の name と id を対応付ける
        if role == "assistant" and isinstance(content, list):
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                tool_name = block.get("name")
                if not isinstance(tool_name, str) or not tool_name:
                    continue
                tool_id = block.get("id")
                if isinstance(tool_id, str) and tool_id:
                    tool_name_by_id[tool_id] = tool_name
            continue

        if role != "user" or not isinstance(content, list):
            continue

        # tool_result ブロックを収集する
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue

            text = _extract_tool_result_text(block)
            if text:
                result["all_outputs"].append(text)

            tool_name = tool_name_by_id.get(_get_tool_result_id(block), "")
            if tool_name:
                if tool_name not in known_tool_names:
                    tool_names_used.append(tool_name)
                    known_tool_names.add(tool_name)

                lower_name = tool_name.lower()
                if tool_name == "Bash" or lower_name == "bash":
                    result["has_bash"] = True
                    if text:
                        result["bash_outputs"].append(text)

                if tool_name in _MUTATION_TOOL_NAMES:
                    result["has_mutation_tool"] = True

                if any(keyword in lower_name for keyword in _MCP_TEST_TOOL_KEYWORDS):
                    result["has_mcp_test_tool"] = True

    result["tool_names_used"] = tool_names_used
    return result


def had_tools_in_current_turn(transcript_path: str, trigger_tools: set[str]) -> bool:
    """直前のユーザー入力以降、指定ツールが呼ばれたか確認する（後方互換）。"""
    if not trigger_tools:
        return False
    scan = scan_transcript_tool_outputs(transcript_path)
    for tool_name in scan["tool_names_used"]:
        if tool_name in trigger_tools:
            return True
    return False


def extract_assistant_message(hook_input: dict) -> str:
    """フック入力から最後のアシスタントメッセージのテキストを取得する。"""
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


# --- テストフレームワーク出力検出 ---

_FAILURE_OUTPUT_PATTERNS = [
    re.compile(r"\bFAILED\b", re.IGNORECASE),
    re.compile(r"\bFAIL\b(?!\w)", re.IGNORECASE),
    re.compile(r"\bAssertionError\b", re.IGNORECASE),
    re.compile(r"\b[A-Z]\w*Error:"),  # Python例外クラス形式（CamelCase）のみ。"No Error:" 等の誤検出を防ぐ
    re.compile(r"\bTraceback\b", re.IGNORECASE),
    re.compile(r"\b0 passed\b", re.IGNORECASE),
    re.compile(r"\b[1-9]\d*\s+failed\b", re.IGNORECASE),
    re.compile(r"\b[1-9]\d*\s+failures?\b", re.IGNORECASE),
]

_SUCCESS_OUTPUT_PATTERNS = [
    re.compile(r"\b\d+\s+passed\b", re.IGNORECASE),
    re.compile(r"===.*\bpassed\b.*===", re.IGNORECASE),
    re.compile(r"\bPASSED\b"),
    re.compile(r"\bRan\s+\d+\s+tests?\s+in\b", re.IGNORECASE),
    re.compile(r"\bTests:\s+\d+\s+passed\b", re.IGNORECASE),
    re.compile(r"(?m)^PASS\s"),
    re.compile(r"(?m)^\s*✓\s"),
    re.compile(r"\bok\s+\S+\s+[\d.]+s\b", re.IGNORECASE),
    re.compile(r"(?m)^--- PASS:"),
    re.compile(r"\btest result:\s+ok\b", re.IGNORECASE),
    re.compile(r"\b\d+\s+passed;\s+0\s+failed\b", re.IGNORECASE),
    re.compile(r"(?m)^OK$"),
    re.compile(r"\b\d+\s+passing\b", re.IGNORECASE),
    re.compile(r"\b\d+\s+examples?,\s+0\s+failures?\b", re.IGNORECASE),
    re.compile(r"\bAll tests passed\b", re.IGNORECASE),
]

_TEST_COMMAND_PATTERNS = [
    re.compile(r"\bpytest\b", re.IGNORECASE),
    re.compile(r"\bpython\s+-m\s+pytest\b", re.IGNORECASE),
    re.compile(r"\bnpm\s+test\b", re.IGNORECASE),
    re.compile(r"\byarn\s+test\b", re.IGNORECASE),
    re.compile(r"\bpnpm\s+test\b", re.IGNORECASE),
    re.compile(r"\bvitest\b", re.IGNORECASE),
    re.compile(r"\bjest\b", re.IGNORECASE),
    re.compile(r"\bgo\s+test\b", re.IGNORECASE),
    re.compile(r"\bcargo\s+test\b", re.IGNORECASE),
    re.compile(r"\brspec\b", re.IGNORECASE),
]


def detect_test_framework_output(text: str) -> bool:
    """典型的なテストフレームワーク成功出力を検出する。失敗パターンがあれば False。"""
    cleaned = strip_ansi(text)
    if not cleaned:
        return False
    for pattern in _FAILURE_OUTPUT_PATTERNS:
        if pattern.search(cleaned):
            return False
    for pattern in _SUCCESS_OUTPUT_PATTERNS:
        if pattern.search(cleaned):
            return True
    return False


def detect_test_command_in_output(text: str) -> bool:
    """Bash 出力中にテストコマンド実行の痕跡があるか確認する。"""
    cleaned = strip_ansi(text)
    if not cleaned:
        return False
    for pattern in _TEST_COMMAND_PATTERNS:
        if pattern.search(cleaned):
            return True
    return False
