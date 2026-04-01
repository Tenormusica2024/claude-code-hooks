# -*- coding: utf-8 -*-
from __future__ import annotations

import io
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

# グローバル CLAUDE.md の固定パス
GLOBAL_CLAUDE_MD = Path(r"C:\Users\Tenormusica\.claude\CLAUDE.md")

# トリガー: 「グローバルCLAUDE.md」を含み、追記・更新・記載のいずれかを含むプロンプト
# 大文字小文字は問わない（CLAUDE.md 部分）
GLOBAL_TRIGGER_RE = re.compile(
    r"グローバル(?:Claude|CLAUDE)\.md",
    re.IGNORECASE,
)
APPEND_ACTION_RE = re.compile(
    r"(?:を更新して|に追記して|に記載して)",
)


def configure_stdio() -> None:
    if sys.platform == "win32":
        sys.stdin = io.TextIOWrapper(
            sys.stdin.buffer,
            encoding="utf-8",
            errors="replace",
        )
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer,
            encoding="utf-8",
            errors="replace",
        )
        sys.stderr = io.TextIOWrapper(
            sys.stderr.buffer,
            encoding="utf-8",
            errors="replace",
        )


def log_error(message: str) -> None:
    print(message, file=sys.stderr)


def load_payload() -> dict[str, object] | None:
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
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup_path = target_file.with_name(
        f"{target_file.name}.{timestamp}.bak"
    ).resolve(strict=False)
    try:
        shutil.copy2(target_file, backup_path)
        return backup_path
    except Exception as exc:
        log_error(f"Failed to create backup for {target_file}: {exc}")
        return None


def get_history_path(cwd: Path) -> Path:
    return (cwd / ".claude" / "updates" / "doc_update_history.md").resolve(strict=False)


def ensure_history_dir(history_path: Path) -> None:
    history_path.parent.mkdir(parents=True, exist_ok=True)


def is_triggered(prompt: str) -> bool:
    """「グローバルCLAUDE.md」＋追記アクションの両方がある場合のみ発火する。"""
    return bool(GLOBAL_TRIGGER_RE.search(prompt) and APPEND_ACTION_RE.search(prompt))


def build_append_context(
    target_file: Path,
    history_path: Path,
    backup_path: Path | None,
) -> str:
    backup_text = (
        f"{backup_path} (use this for rollback if needed)"
        if backup_path is not None
        else "Backup could not be created; proceed carefully and do not rely on rollback."
    )
    return (
        "[GLOBAL CLAUDE.MD APPEND TRIGGERED]\n"
        "The user wants to append to the global CLAUDE.md. Perform the append now as part of your response.\n\n"
        f"Target file: {target_file}\n"
        f"Backup saved at: {backup_text}\n\n"
        "Steps to perform:\n"
        f"1. Read the current content of {target_file} using the Read tool\n"
        "2. Determine what to append based on the user's request in the current session\n"
        "3. Append-only: do NOT rewrite, reorder, or delete any existing content\n"
        "4. Do NOT run consistency checks, do NOT remove stale info, do NOT reduce token count\n"
        "5. Write the appended content back to {target_file} using the Write tool\n"
        "   - Keep additions SHORT and KEY-POINT-ONLY (なるべく短く要点のみで言語化する)\n"
        "   - Place the new entry in the most relevant existing section, or at the end if no section fits\n"
        f"6. Append a brief note to {history_path}:\n"
        '   - Format: "=== YYYY-MM-DD HH:MM:SS ===\\nAppended: {{brief summary of what was added}}\\n\\n"\n\n'
        "Constraints:\n"
        "- This is the GLOBAL Claude instructions file — any change is permanent and affects ALL sessions\n"
        "- Confirm with the user before writing if the scope of the append is ambiguous\n"
        "- Never rewrite or restructure existing sections without explicit user instruction"
    ).replace("{target_file}", str(target_file))


def main() -> int:
    configure_stdio()
    payload = load_payload()
    if payload is None:
        return 0

    prompt = str(payload.get("prompt", ""))
    stop_hook_active = bool(payload.get("stop_hook_active", False))

    if stop_hook_active:
        return 0

    if not is_triggered(prompt):
        return 0

    target_file = GLOBAL_CLAUDE_MD

    if not target_file.exists():
        result = {
            "additionalContext": (
                "[GLOBAL CLAUDE.MD APPEND TRIGGERED]\n"
                f"{target_file} not found. Should I create it?\n\n"
                "Only ask the user for confirmation. Do not create or modify any files until the user confirms."
            )
        }
        json.dump(result, sys.stdout, ensure_ascii=False)
        return 0

    backup_path = backup_target_file(target_file)

    # 履歴はグローバルCLAUDE.mdと同じディレクトリ内に集約する
    history_path = (target_file.parent / "updates" / "doc_update_history.md").resolve(strict=False)
    try:
        ensure_history_dir(history_path)
    except Exception as exc:
        log_error(f"Failed to create history directory for {history_path}: {exc}")

    context_str = build_append_context(target_file, history_path, backup_path)
    result = {"additionalContext": context_str}
    json.dump(result, sys.stdout, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
