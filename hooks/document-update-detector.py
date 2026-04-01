# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# hook_utils（同ディレクトリ）から共通ユーティリティを読み込む
sys.path.insert(0, str(Path(__file__).parent))
from hook_utils import (
    backup_target_file,
    configure_stdio,
    ensure_history_dir,
    load_payload,
    log_error,
)

# "CLAUDE.md" の大文字小文字バリアントすべてに一致させる
CLAUDE_TRIGGER_RE = re.compile(r"CLAUDE\.md", re.IGNORECASE)
# CLAUDE.md への更新系アクション語（追記系は CLAUDE_APPEND_ACTION_RE で別管理）
# 読み取り指示（「確認して」「読んで」等）では発火しない
CLAUDE_ACTION_RE = re.compile(
    r"(?:を更新して|に記載して|に反映して|を修正して)",
)
# CLAUDE.md への追記系アクション語。70% 縮小なしの追記専用コンテキストを注入する
CLAUDE_APPEND_ACTION_RE = re.compile(r"(?:に追記して|に追加して)")
# マスタードキュメントトリガーとアクション語（読み取り指示では発火しない）
MASTER_TRIGGER_RE = re.compile(r"マスタードキュメント")
MASTER_ACTION_RE = re.compile(
    r"(?:を更新して|に追記して|に記載して|に追加して|に反映して|を修正して)",
)
# 「ドキュメントを更新して」等の省略形（CLAUDE.md と明示しない場合）→ cwd/CLAUDE.md をデフォルトターゲット
# 「マスタードキュメント」は MASTER_TRIGGER_RE が先に処理するため、detect_trigger でリターン済みの後に評価される
DOC_SHORTHAND_TRIGGER_RE = re.compile(r"ドキュメント(?!の更新が必要|を確認して|を読んで|を参照)")
DOC_SHORTHAND_ACTION_RE = re.compile(r"(?:を更新して|に記載して|に反映して|を修正して)")
DOC_SHORTHAND_APPEND_RE = re.compile(r"(?:に追記して|に追加して)")
QUOTED_MD_PATH_RE = re.compile(r"""["']([^"'\r\n]+?\.md)["']""", re.IGNORECASE)
# 参照文脈の quoted path を除外するパターン。
# 「'notes.md' を参考にマスタードキュメントを更新して」のように
# quoted path が参照渡しで書かれたときに、誤ってそちらをターゲットにするのを防ぐ。
# 日本語の語順: quoted_path が先、参照動詞が後（例: 'notes.md' を参考に）
REFERENCE_QUOTED_PATH_RE = re.compile(
    r"""["'][^"'\r\n]+?\.md["']\s*(?:を参考に|を参照して|を読んで|を確認して|を見ながら)""",
    re.IGNORECASE,
)
# グローバルCLAUDE.md 専用フック（global-claude-md-appender）が担当するプロンプトを除外する
# \s* で「グローバル CLAUDE.md」（空白入り）にも対応する
# これにより両フックが同時発火して cwd/CLAUDE.md へ70%縮小コンテキストが注入される問題を防ぐ
GLOBAL_CLAUDE_GUARD_RE = re.compile(r"グローバル\s*(?:Claude|CLAUDE)\.md", re.IGNORECASE)


def resolve_path(path_str: str, base_dir: Path | None = None) -> Path:
    path = Path(path_str)
    if not path.is_absolute() and base_dir is not None:
        path = base_dir / path
    return path.resolve(strict=False)


def extract_explicit_md_path(prompt: str, cwd: Path) -> Path | None:
    """更新対象として明示指定された quoted path のみ返す。

    quoted path のみを受理し、unquoted の .md パスは無視する。
    さらに参照文脈（「'notes.md' を参考に〜」等）で渡された quoted path は
    REFERENCE_QUOTED_PATH_RE で除外し、誤ってターゲットに採用するのを防ぐ。

    カスタムターゲットを指定したい場合は必ずパスを引用符で囲む:
      ✅ 「"path/to/master.md" のマスタードキュメントを更新して」
      ❌  「'notes.md' を参考にマスタードキュメントを更新して」（参照扱いで除外）
    """
    # 参照文脈の quoted path をプロンプトから除いてから探索する
    cleaned = REFERENCE_QUOTED_PATH_RE.sub("", prompt)
    quoted_match = QUOTED_MD_PATH_RE.search(cleaned)
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


def build_claude_append_context(
    target_file: Path,
    history_path: Path,
    backup_path: Path | None,
) -> str:
    """追記専用コンテキスト。70% 縮小・整合性チェックは行わない。"""
    backup_text = (
        f"{backup_path} (use this for rollback if needed)"
        if backup_path is not None
        else "Backup could not be created; proceed carefully and do not rely on rollback."
    )
    return (
        "[DOCUMENT APPEND TRIGGERED]\n"
        "The user wants to append to CLAUDE.md. Perform the append now as part of your response.\n\n"
        f"Target file: {target_file}\n"
        f"Backup saved at: {backup_text}\n\n"
        "Steps to perform:\n"
        f"1. Read the current content of {target_file} using the Read tool\n"
        "2. Append-only: do NOT rewrite, reorder, or delete any existing content\n"
        "3. Do NOT run consistency checks, do NOT remove stale info, do NOT reduce token count\n"
        f"4. Write the appended content back to {target_file} using the Write tool\n"
        "   - Keep additions SHORT and KEY-POINT-ONLY\n"
        "   - Place the new entry in the most relevant existing section, or at the end if no section fits\n"
        f"5. Append a brief note to {history_path}:\n"
        '   - Format: "=== YYYY-MM-DD HH:MM:SS 形式の現在日時 ===\\nAppended: {brief summary}\\n\\n"\n\n'
        "Structural rules:\n"
        "- Preserve existing section headers\n"
        "- Do NOT add new sections unless clearly necessary\n"
        "- Keep the Meta section (rules for writing rules) intact"
    )


def extract_purpose_comment(md_file: Path) -> str:
    """ファイル先頭の <!-- 目的: ... --> コメントを読み取って返す。
    コメントが見つからない場合はファイル名（拡張子なし）を返す。"""
    try:
        # 先頭512バイトのみ読んでパフォーマンスを確保する
        with md_file.open(encoding="utf-8", errors="replace") as f:
            head = f.read(512)
        m = re.search(r"<!--\s*目的:\s*(.+?)\s*-->", head)
        if m:
            return m.group(1).strip()
    except OSError:
        pass
    return md_file.stem


def scan_doc_candidates(cwd: Path) -> list[tuple[str, Path]]:
    """更新候補となる .md ファイルを列挙し (目的説明, パス) のリストを返す。

    優先順序:
      1. cwd/CLAUDE.md（プロジェクトルートのインデックス）
      2. cwd/rules/*.md（rules/ 配下の詳細仕様ファイル）
    """
    candidates: list[tuple[str, Path]] = []

    claude_md = (cwd / "CLAUDE.md").resolve(strict=False)
    if claude_md.exists():
        candidates.append(("プロジェクト全体のインデックス・軽量ルール", claude_md))

    rules_dir = cwd / "rules"
    if rules_dir.is_dir():
        for md_file in sorted(rules_dir.glob("*.md")):
            if md_file.is_file():
                purpose = extract_purpose_comment(md_file)
                candidates.append((purpose, md_file))

    return candidates


def build_doc_smart_context(cwd: Path, history_path: Path) -> str:
    """「ドキュメントを更新して」省略形用コンテキスト。

    候補ファイルを列挙して Claude に適切なターゲットを選ばせ、
    選択後に通常の更新手順（claude コンテキスト相当）を実行させる。
    バックアップは Claude がターゲットを確定した後に自己判断で行う。
    """
    candidates = scan_doc_candidates(cwd)

    if not candidates:
        # 候補が見つからない場合は CLAUDE.md 作成を提案する
        return (
            "[DOCUMENT UPDATE TRIGGERED]\n"
            f"No markdown documents found in {cwd}. "
            "Should I create a CLAUDE.md in this directory?\n\n"
            "Only ask the user for confirmation. Do not create any files until confirmed."
        )

    lines = ["[DOCUMENT UPDATE TRIGGERED]"]
    lines.append(
        "The user said 'ドキュメントを更新して' without specifying a target file. "
        "Select the most appropriate document from the candidates below based on "
        "what was discussed in the current session, then perform the update.\n"
    )
    lines.append("## Candidate documents\n")
    for i, (purpose, path) in enumerate(candidates, start=1):
        lines.append(f"{i}. {path}  — {purpose}")
    lines.append("")
    lines.append("## Steps to perform\n")
    lines.append(
        "1. Decide which document best matches the current session context "
        "(prefer a specific rules/ file over CLAUDE.md when the change is narrow in scope)"
    )
    lines.append("2. Read the selected file using the Read tool")
    lines.append("3. Consistency check: identify contradictions and stale references")
    lines.append("4. Incorporate new learnings from the current session")
    lines.append(
        "5. Rebalance: aim for the updated document to be no more than 70% "
        "of the current token count while preserving all essential rules"
    )
    lines.append("6. Write the updated content back using the Write tool")
    lines.append(f"7. Append a brief update note to {history_path}:")
    lines.append(
        '   - Format: "=== YYYY-MM-DD HH:MM:SS 形式の現在日時 ===\\n'
        'Changes: {target file} — {brief summary}\\n\\n"'
    )
    lines.append("")
    lines.append("## Structural rules\n")
    lines.append("- Preserve existing section headers")
    lines.append("- Do NOT add new sections unless clearly necessary")
    lines.append("- Merge duplicate rules rather than keeping both")

    return "\n".join(lines)


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
    # MASTER_ACTION_RE を必須とし、読み取り指示（「確認して」等）では発火しない。
    if MASTER_TRIGGER_RE.search(prompt) and MASTER_ACTION_RE.search(prompt):
        # extract_explicit_md_path は quoted path のみを受理し、
        # 参照文脈の quoted path（「'notes.md' を参考に〜」等）は除外する。
        explicit_path = extract_explicit_md_path(prompt, cwd)
        if explicit_path is not None:
            return "master", explicit_path
        # デフォルト: 「マスタードキュメント」→ master コンテキスト（進捗更新向け）で cwd/CLAUDE.md を対象
        return "master", (cwd / "CLAUDE.md").resolve(strict=False)

    # CLAUDE.md が言及されていても、書き込みアクション語がなければ発火しない。
    # 「CLAUDE.md を確認して」「CLAUDE.md を読んで」等の参照指示は対象外。
    if CLAUDE_TRIGGER_RE.search(prompt):
        is_append = bool(CLAUDE_APPEND_ACTION_RE.search(prompt))
        is_update = bool(CLAUDE_ACTION_RE.search(prompt))
        if is_append or is_update:
            # quoted path（CLAUDE.md 以外）があればそちらをターゲットにする
            explicit_path = extract_explicit_md_path(prompt, cwd)
            target = explicit_path if explicit_path is not None else (cwd / "CLAUDE.md").resolve(strict=False)
            # 追記系（に追記して/に追加して）は70%縮小なしの追記専用コンテキスト
            if is_append:
                return "claude_append", target
            # 更新系（を更新して/に記載して/に反映して/を修正して）は70%縮小コンテキスト
            return "claude", target

    # 「ドキュメントを更新して」省略形 → 候補ファイルを列挙して Claude に選ばせる（doc_smart）。
    # quoted path があればそちらをターゲットに確定して通常モードで処理する。
    # マスタードキュメント・グローバルCLAUDE.md のガードはここより上で早期リターン済み。
    # 観察文（「ドキュメントの更新が必要」等）はアクション語にマッチしないため発火しない。
    if DOC_SHORTHAND_TRIGGER_RE.search(prompt):
        explicit_path = extract_explicit_md_path(prompt, cwd)
        if explicit_path is not None:
            # 明示パスがあれば通常の claude モードで処理（候補選択不要）
            if DOC_SHORTHAND_APPEND_RE.search(prompt):
                return "claude_append", explicit_path
            return "claude", explicit_path
        if DOC_SHORTHAND_APPEND_RE.search(prompt) or DOC_SHORTHAND_ACTION_RE.search(prompt):
            # 明示パスなし → cwd を渡して候補選択モードへ
            return "doc_smart", cwd

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

    # doc_smart は特定ターゲットを持たない（target_file は cwd）。
    # バックアップ・存在確認をスキップして候補列挙コンテキストを注入する。
    if trigger_kind == "doc_smart":
        history_path = get_history_path(target_file)  # target_file == cwd
        try:
            ensure_history_dir(history_path)
        except Exception as exc:
            log_error(f"Failed to create history directory for {history_path}: {exc}")
        context_str = build_doc_smart_context(target_file, history_path)
        result = {"additionalContext": context_str}
        json.dump(result, sys.stdout, ensure_ascii=False)
        return 0

    # 存在確認は doc_smart 以外の全 trigger_kind に対して共通で実行する。
    # この分岐でのみ早期リターンするため、以降の backup_target_file() や
    # ensure_history_dir() は target_file が存在する場合にしか到達しない。
    if not target_file.exists():
        result = {"additionalContext": build_missing_context(target_file)}
        json.dump(result, sys.stdout, ensure_ascii=False)
        return 0

    # ここに到達した時点でターゲットファイルの存在が保証されている。
    backup_path = backup_target_file(target_file)

    history_path = get_history_path(cwd)
    try:
        ensure_history_dir(history_path)
    except Exception as exc:
        log_error(f"Failed to create history directory for {history_path}: {exc}")

    if trigger_kind == "claude":
        context_str = build_claude_context(target_file, history_path, backup_path)
    elif trigger_kind == "claude_append":
        context_str = build_claude_append_context(target_file, history_path, backup_path)
    else:
        context_str = build_master_context(target_file, history_path, backup_path)

    result = {"additionalContext": context_str}
    json.dump(result, sys.stdout, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
