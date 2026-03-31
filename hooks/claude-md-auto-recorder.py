# -*- coding: utf-8 -*-
from __future__ import annotations
"""
Stop Hook: CLAUDE.md更新の確認をユーザーに丸投げする行為を検出 & ブロック

stdinからClaude CodeのStop hook JSONを受け取り、
last_assistant_messageに「CLAUDE.mdに記録する？」系の確認フレーズが含まれていたら
stdoutにblock JSONを出力して自己修正ターンを強制する。

検出条件（AND条件）:
  1. "CLAUDE.md" への言及
  2. 記録・追記・更新系のアクションワード（約10種）
  3. 質問・確認を表す文末表現（？ / でしょうか / しますか 等）

設計原則:
  - 「CLAUDE.md」単独ではblockしない（文中での言及を誤検知しないため）
  - AND条件で絞ることで、レビュー系プロンプトの「CLAUDE.mdに追記しておきました」等は素通り
  - blockメッセージ内に品質ゲート指示を埋め込み、細かすぎる記録はスキップさせる
"""

import io
import json
import re
import sys

# Windows環境でstdin/stdout/stderrのエンコーディングをUTF-8に強制
if sys.platform == "win32":
    sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


# --- CLAUDE.md言及パターン ---
# 検出の起点。これを含む文脈内を追加チェックする
CLAUDE_MD_PATTERN = re.compile(r"CLAUDE\.md", re.IGNORECASE)

# --- アクションワード（記録・更新系10種）---
# CLAUDE.mdへの書き込みを示す動詞群の語幹マッチ。
# 「残しておく」「残しておきます」「残しておきましょうか」等の活用形を全てカバーするため語幹で広めにマッチ。
# 除外パターン（完了・否定）で完了形を後から除去する。
ACTION_PATTERNS = [
    r"残しておき?",       # 残しておく / 残しておきます / 残しておきましょう
    r"記録し",             # 記録する / 記録して / 記録します / 記録しておきます
    r"書いておき?",        # 書いておく / 書いておきます
    r"追記し",             # 追記する / 追記して / 追記します / 追記しておきます
    r"メモしておき?",
    r"保存しておき?",
    r"書き込[みむ]",        # 書き込む / 書き込み
    r"更新し",             # 更新する / 更新して / 更新します / 更新しておきます
    r"追加し",             # 追加する / 追加して / 追加します
]
ACTION_RE = re.compile("|".join(ACTION_PATTERNS))

# --- 質問・確認表現（文末の確認を表す表現）---
# これが含まれることで「ユーザーへの確認」と判断する
QUESTION_PATTERNS = [
    r"[？?]",
    r"でしょうか",
    r"いいですか",
    r"ますか",       # しますか / おきますか / ていいですか 等を包含
    r"どうですか",
]
QUESTION_RE = re.compile("|".join(QUESTION_PATTERNS))

# --- 除外パターン ---
# 「記録しない」「スキップ」等の明示的な否定が同一文脈にある場合はblockしない
EXCLUSION_PATTERNS = [
    # 完了報告（記録済み）= ユーザーへの確認ではない
    r"(?:追記|記録|更新)(?:した|しました|済み|完了)",
    r"(?:書いておき|保存し)ました",
    # 明示的な否定・スキップ
    r"記録(?:しない|不要|はしない)",
    r"追記しない",
    r"書かない",
    r"スキップ",
    r"記録(?:は)?(?:省略|不要)",
    # 引用・参照テキスト内（hook仕様の説明やコード例でパターンに言及しているケース）
    # 例: 「CLAUDE.mdに書いておく？」という... → 誤検知を防ぐ
    r"[「『\"].*CLAUDE\.md.*[」』\"]",
    r"(?:例|例えば|たとえば|パターン|フレーズ|ワード|表現).*CLAUDE\.md",
    r"CLAUDE\.md.*(?:パターン|フレーズ|ワード|表現|という)",
]
EXCLUSION_RE = re.compile("|".join(EXCLUSION_PATTERNS), re.IGNORECASE)

# CLAUDE.md言及から前後に取るコンテキストウィンドウ（文字数）
CONTEXT_WINDOW = 120


def extract_assistant_message(hook_input: dict) -> str:
    """Stop hookのJSONからアシスタントメッセージテキストを抽出する。"""
    for key in ("last_assistant_message", "assistant_message", "message", "content", "output"):
        val = hook_input.get(key)
        if val and isinstance(val, str):
            return val

    transcript_path = hook_input.get("transcript_path")
    if transcript_path:
        try:
            with open(transcript_path, "r", encoding="utf-8") as f:
                transcript = json.load(f)
            if isinstance(transcript, list):
                for msg in reversed(transcript):
                    if msg.get("role") == "assistant":
                        content = msg.get("content", "")
                        if isinstance(content, list):
                            texts = []
                            for block in content:
                                if isinstance(block, dict) and block.get("type") == "text":
                                    texts.append(block.get("text", ""))
                                elif isinstance(block, str):
                                    texts.append(block)
                            return "\n".join(texts)
                        return str(content)
        except (json.JSONDecodeError, FileNotFoundError, PermissionError, KeyError):
            pass

    return ""


def detect_claude_md_confirmation(text: str) -> list[dict]:
    """CLAUDE.md更新確認のユーザー丸投げパターンを検出する。

    検出条件（AND）:
      1. CLAUDE.md への言及
      2. 記録・更新系アクションワード
      3. 質問・確認表現
    除外: 否定・完了・スキップの明示がある場合
    """
    findings = []

    for m in CLAUDE_MD_PATTERN.finditer(text):
        # CLAUDE.md言及の前後コンテキストを取得
        ctx_start = max(0, m.start() - CONTEXT_WINDOW)
        ctx_end = min(len(text), m.end() + CONTEXT_WINDOW)
        context = text[ctx_start:ctx_end]

        # 除外パターンが含まれていればスキップ
        if EXCLUSION_RE.search(context):
            continue

        # アクションワード + 質問表現の両方がコンテキスト内にあるか確認
        has_action = ACTION_RE.search(context)
        has_question = QUESTION_RE.search(context)

        if has_action and has_question:
            findings.append({
                "matched_claude_md": m.group(),
                "action": has_action.group(),
                "question": has_question.group(),
                "context": context.strip(),
            })

    return findings


def main():
    try:
        raw_input = sys.stdin.read()
        if not raw_input.strip():
            sys.exit(0)
        hook_input = json.loads(raw_input)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    # block後の再実行時はスキップ（無限ループ防止）
    if hook_input.get("stop_hook_active"):
        sys.exit(0)

    assistant_message = extract_assistant_message(hook_input)
    if not assistant_message:
        sys.exit(0)

    findings = detect_claude_md_confirmation(assistant_message)
    if not findings:
        sys.exit(0)

    # block JSONをstdoutに出力
    # blockメッセージ内に品質ゲートを埋め込み：細かすぎる記録はスキップさせる
    reason = (
        "[CLAUDE-MD RECORDING GATE BLOCKED] "
        "You asked the user whether to write to CLAUDE.md instead of deciding yourself. "
        "Do NOT ask — act immediately based on the following quality gate:\n"
        "  WRITE if: reusable lesson, recurring pattern, important constraint, or architectural decision\n"
        "  SKIP if: one-time observation, trivial detail, or minor review finding not worth tracking\n"
        "If it meets the WRITE criteria: follow the Self-Improvement Loop rule and write to the "
        "appropriate CLAUDE.md section now, without asking. "
        "If it meets the SKIP criteria: silently drop the recording and continue."
    )
    json.dump({"decision": "block", "reason": reason}, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
