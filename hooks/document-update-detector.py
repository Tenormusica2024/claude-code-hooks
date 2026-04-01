# -*- coding: utf-8 -*-
from __future__ import annotations

import io
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

# "CLAUDE.md" の大文字小文字バリアントすべてに一致させる
CLAUDE_TRIGGER_RE = re.compile(r"CLAUDE\.md", re.IGNORECASE)
MASTER_TRIGGER_RE = re.compile(r"マスタードキュメント")
QUOTED_MD_PATH_RE = re.compile(r"""["']([^"'\r\n]+?\.md)["']""", re.IGNORECASE)
# グローバルCLAUDE.md 専用フック（global-claude-md-appender）が担当するプロンプトを除外する
# これにより両フックが同時発火して cwd/CLAUDE.md へ70%縮小コンテキストが注入される問題を防ぐ
GLOBAL_CLAUDE_GUARD_RE = re.compile(r"グローバル(?:Claude|CLAUDE)\.md", re.IGNORECASE)


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


def resolve_path(path_str: str, base_dir: Path | None = None) -> Path:
    path = Path(path_str)
    if not path.is_absolute() and base_dir is not None:
        path = base_dir / path
    return path.resolve(strict=False)


def extract_master_doc_path(prompt: str, cwd: Path) -> Path | None:
    """マスタードキュメントの更新対象として明示指定されたパスのみ返す。

    quoted path のみを受理し、unquoted の .md パスは無視する。
    これにより「参考に notes.md も見て」のような参照パスを誤って
    更新対象に取り込むバグを防ぐ。

    カスタムマスタードキュメントを指定したい場合は必ずパスを引用符で囲む:
      ✅ 「"path/to/master.md" のマスタードキュメントを更新して」
      ❌  path/to/master.md のマスタードキュメントを更新して（参照扱いになる）
    """
    quoted_match = QUOTED_MD_PATH_RE.search(prompt)
    if quoted_match:
        path = resolve_path(quoted_match.group(1), cwd)
        # CLAUDE.md はコンテキスト参照として除外（デフォルトパスに委ねる）
        if path.name.upper() != "CLAUDE.MD":
            return path
    return None


def get_history_path(cwd: Path) -> Path:
    # 履歴は対象ファイルの場所に関わらず常に cwd/.claude/updates/ に集約する。
    # 明示パスが別ディレクトリのファイルを指す場合も分散しない。
    return (
        cwd / ".claude" / "updates" / "doc_update_history.md"
    ).resolve(strict=False)


def ensure_history_dir(history_path: Path) -> None:
    history_path.parent.mkdir(parents=True, exist_ok=True)


def backup_target_file(target_file: Path) -> Path | None:
    # タイムスタンプ付きバックアップ名で上書きを防ぐ
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup_path = target_file.with_name(f"{target_file.name}.{timestamp}.bak").resolve(strict=False)
    try:
        shutil.copy2(target_file, backup_path)
        return backup_path
    except Exception as exc:
        log_error(f"Failed to create backup for {target_file}: {exc}")
        return None


def build_missing_context(target_file: Path) -> str:
    """ターゲットファイルが存在しない場合にClaudeへ作成確認を促すコンテキストを返す。"""
    return (
        "[DOCUMENT UPDATE TRIGGERED]\n"
        f"{target_file} not found. Should I create one?\n\n"
        "Only ask the user for confirmation. Do not create or modify any files until the user confirms."
    )


def build_claude_context(
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
        "[DOCUMENT UPDATE TRIGGERED]\n"
        "The user wants to update CLAUDE.md. Please perform this update now as part of your response.\n\n"
        f"Target file: {target_file}\n"
        f"Backup saved at: {backup_text}\n\n"
        "Steps to perform:\n"
        f"1. Read the current content of {target_file} using the Read tool\n"
        "2. Consistency check: identify internal contradictions and rules that conflict with information discussed in the current session\n"
        "3. Remove stale info: remove references to deleted/renamed files, deprecated tools, or descriptions contradicting current operations\n"
        "4. Incorporate new learnings: add any important patterns, decisions, or rules that emerged in the current session\n"
        "5. Rebalance: aim for the updated document to be no more than 70% of the current token count while preserving all essential rules\n"
        f"6. Write the updated content back to {target_file} using the Write tool\n"
        f"7. Compute a diff summary and append it to {history_path}:\n"
        '   - Format: "=== YYYY-MM-DD HH:MM:SS 形式の現在日時 ===\\nChanges: {brief summary of what changed}\\n\\n"\n\n'
        "Structural rules for CLAUDE.md update:\n"
        "- Preserve existing section headers\n"
        "- Do NOT add new sections unless clearly necessary\n"
        "- Keep the Meta section (rules for writing rules) intact\n"
        "- Merge duplicate rules rather than keeping both"
    )


def build_master_context(
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
        "[DOCUMENT UPDATE TRIGGERED]\n"
        "The user wants to update the master progress document. Please perform this update now as part of your response.\n\n"
        f"Target file: {target_file}\n"
        f"Backup saved at: {backup_text}\n\n"
        "Steps to perform:\n"
        f"1. Read the current content of {target_file} using the Read tool\n"
        "2. Update project statuses based on work done in the current session\n"
        "3. Add entries for any new projects/repositories worked on this session\n"
        '4. Update "Last activity" dates and descriptions for touched projects\n'
        "5. Remove or archive clearly completed/abandoned project entries (only if obviously done)\n"
        "6. Preserve the document's existing format, section structure, and conventions exactly\n"
        f"7. Write the updated content back to {target_file} using the Write tool\n"
        f"8. Append a brief update note to {history_path}:\n"
        '   - Format: "=== YYYY-MM-DD HH:MM:SS 形式の現在日時 ===\\nChanges: {brief summary}\\n\\n"\n\n'
        "Important: Do NOT change the document format. Only update content within the existing structure."
    )


def detect_trigger(
    prompt: str,
    cwd: Path,
) -> tuple[str, Path] | None:
    # グローバルCLAUDE.md を対象とする要求は global-claude-md-appender に委ねる。
    # CLAUDE_TRIGGER_RE はグローバル指定も誤検知するため、ここで早期リターンして
    # cwd/CLAUDE.md への 70% 縮小コンテキストが二重注入されるのを防ぐ。
    if GLOBAL_CLAUDE_GUARD_RE.search(prompt):
        return None

    # マスタードキュメントトリガーを CLAUDE.md トリガーより先に評価する。
    # 両方を含むプロンプトでも「マスタードキュメント」の意図が優先される。
    if MASTER_TRIGGER_RE.search(prompt):
        # extract_master_doc_path は quoted path のみを受理し、
        # 「参考に notes.md も見て」のような参照パスは無視する（extract_explicit_md_path との違い）。
        explicit_path = extract_master_doc_path(prompt, cwd)
        if explicit_path is not None:
            return "master", explicit_path
        # デフォルト: 「マスタードキュメント」= cwd の CLAUDE.md（プロジェクト最上位ルール）
        return "claude", (cwd / "CLAUDE.md").resolve(strict=False)

    if CLAUDE_TRIGGER_RE.search(prompt):
        return "claude", (cwd / "CLAUDE.md").resolve(strict=False)

    return None


def main() -> int:
    configure_stdio()
    payload = load_payload()
    if payload is None:
        return 0

    prompt = str(payload.get("prompt", ""))
    raw_cwd = str(payload.get("cwd", "")).strip()
    if not raw_cwd:
        # cwd が渡らない異常系では処理しない（os.getcwd() は意図しないパスになりうる）
        log_error("Hook input missing 'cwd'; skipping.")
        return 0
    cwd = resolve_path(raw_cwd)
    stop_hook_active = bool(payload.get("stop_hook_active", False))

    if stop_hook_active:
        return 0

    trigger = detect_trigger(prompt, cwd)
    if trigger is None:
        return 0

    trigger_kind, target_file = trigger

    # 存在確認は claude / master 両方の trigger_kind に対して共通で実行する。
    # この分岐でのみ早期リターンするため、以降の backup_target_file() や
    # ensure_history_dir() は target_file が存在する場合にしか到達しない。
    if not target_file.exists():
        # claude / master 両方で不存在時は作成確認を促すだけ（副作用なし）
        result = {"additionalContext": build_missing_context(target_file)}
        json.dump(result, sys.stdout, ensure_ascii=False)
        return 0

    # ここに到達した時点でターゲットファイルの存在が保証されている。
    # backup_target_file() と ensure_history_dir() はファイル存在後にのみ実行される。
    backup_path = backup_target_file(target_file)

    history_path = get_history_path(cwd)
    try:
        ensure_history_dir(history_path)
    except Exception as exc:
        log_error(f"Failed to create history directory for {history_path}: {exc}")

    if trigger_kind == "claude":
        context_str = build_claude_context(target_file, history_path, backup_path)
    else:
        context_str = build_master_context(target_file, history_path, backup_path)

    result = {"additionalContext": context_str}
    json.dump(result, sys.stdout, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
