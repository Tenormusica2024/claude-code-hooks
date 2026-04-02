# -*- coding: utf-8 -*-
from __future__ import annotations
"""
Stop Hook: テスト・確認作業のユーザー丸投げ検出 & ブロック
stdinからClaude CodeのStop hook JSONを受け取り、
last_assistant_messageにユーザーへのテスト丸投げパターンが含まれていたら
stdoutにblock JSONを出力してセッション終了をブロックし、自己修正ターンを強制する。

検出対象: 「試してみて」「テストしてみて」「手動で」等のテスト委譲表現
除外対象: 管理者権限・ログイン認証・主観的UI確認が必要な場合
"""

import io
import json
import os
import re
import sys

# Windows環境でstdin/stdout/stderrのエンコーディングをUTF-8に強制
if sys.platform == "win32":
    sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


# --- テスト丸投げパターン定義 ---
# 各パターンは (regex, 説明) のタプル
DELEGATION_PATTERNS = [
    # 「〜してみてください」系（テスト・確認・実行の委譲）
    (r"試して(?:みて|ください)", "「試してみて」"),
    (r"テストして(?:みて|ください)", "「テストしてみて」"),
    (r"確認して(?:みて|ください)", "「確認してみて」"),
    (r"実行して(?:みて|ください)", "「実行してみて」"),
    (r"動作確認(?:を)?して(?:みて|ください)", "「動作確認してみて」"),
    (r"検証して(?:みて|ください)", "「検証してみて」"),
    # 「新しいターミナルで」「別のターミナルで」系
    (r"(?:新しい|別の|新規)(?:ターミナル|端末|シェル|コンソール)(?:で|を開いて)", "ターミナル操作の委譲"),
    # 「手動で」系
    (r"手動で(?:実行|テスト|確認|操作|入力)", "手動操作の委譲"),
    (r"手動操作(?:が必要|してください|をお願い)", "手動操作の委譲"),
    # 「ブラウザで開いて」系（自分で確認すべき場合）
    (r"ブラウザで(?:開いて|アクセスして|確認して)(?:みて|ください)", "ブラウザ確認の委譲"),
    # 「以下のコマンドを実行して」系
    (r"以下の(?:コマンド|手順)を(?:実行|試|入力)して(?:みて|ください)", "コマンド実行の委譲"),
    # 「curl で叩いて」系
    (r"curl\s+.*(?:して(?:みて|ください)|叩いて)", "curl実行の委譲"),
]

# --- 除外パターン定義 ---
# これらのパターンが同一文（前後80文字）に含まれていれば検出をスキップ
EXCLUSION_PATTERNS = [
    # 管理者権限が必要
    r"管理者(?:として|権限|で実行)",
    r"(?:admin|administrator|sudo|runas)",
    r"権限(?:が必要|不足|エラー)",
    r"昇格(?:した|して)",
    # ログイン・認証が必要
    r"ログイン(?:が必要|してから|後に|した状態)",
    r"認証(?:が必要|してから|後に|情報)",
    r"(?:サインイン|sign\s*in)(?:が必要|してから|後に)",
    r"(?:2FA|二要素|MFA|CAPTCHA|キャプチャ)",
    r"パスワード(?:を入力|が必要)",
    # 主観的UI確認（ユーザーの目視判断が本当に必要な場合）
    r"(?:見た目|デザイン|レイアウト|色味|フォント)(?:が|を)(?:期待通り|好み|お好み|イメージ通り)",
    r"(?:意図した|期待通りの|想定した)(?:見た目|表示|デザイン)(?:か|になって)",
    r"(?:お好みに|好みに)(?:合う|合って|なって)",
    r"(?:主観的|感覚的)(?:な|に)(?:確認|判断|チェック)",
    # ユーザーしかできない操作の明示的説明
    r"(?:ユーザー|あなた)(?:しか|にしか|だけが|のみ)(?:できない|不可能)",
    r"(?:物理的|実機)(?:な|で)(?:操作|確認|テスト)",
    # 引用・参照テキスト内（記事タイトル等でフレーズに言及しているケース）
    r"[「『\"].*[」』\"]",
    r"(?:タイトル|見出し|記事名|スラッグ).*(?:試|確認|テスト)",
    # Claudeにはできない操作（再起動・セッション操作等）
    r"(?:再起動|リスタート|restart|reboot)(?:して|した後|してから)",
    r"(?:セッション|ターミナル|シェル)(?:を)?(?:再起動|リスタート|閉じて|開き直し)",
    r"(?:/exit|exit|quit).*(?:戻|resume|再開)",
    # テスト完了後の結果報告文脈（丸投げではなく報告）
    r"(?:テスト|検証|確認)(?:が|は)?(?:完了|成功|通過|パス)(?:した|しました)",
    r"(?:動作確認|テスト実行)(?:の)?結果",
    r"(?:正常に|問題なく)(?:動作|機能|実行)(?:して|した|します|しました)",
]


def extract_assistant_message(hook_input: dict) -> str:
    """Stop hookのJSONからアシスタントメッセージテキストを抽出する。
    last_assistant_messageを最優先で確認し、なければtranscript_pathにフォールバック。"""

    # 最優先: hook_input直下のメッセージキー
    for key in ("last_assistant_message", "assistant_message", "message", "content", "output"):
        val = hook_input.get(key)
        if val and isinstance(val, str):
            return val

    # フォールバック: transcript_pathから最新のアシスタントメッセージを取得
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


def get_surrounding_context(text: str, match_start: int, match_end: int, window: int = 80) -> str:
    """マッチ位置の前後window文字を取得する"""
    ctx_start = max(0, match_start - window)
    ctx_end = min(len(text), match_end + window)
    return text[ctx_start:ctx_end]


def is_excluded(context: str) -> bool:
    """除外パターンに該当するかチェック"""
    for pattern in EXCLUSION_PATTERNS:
        if re.search(pattern, context, re.IGNORECASE):
            return True
    return False


def detect_delegation(text: str) -> list[dict]:
    """テスト丸投げパターンを検出する。除外パターンに該当するものはスキップ。"""
    findings = []

    for pattern, description in DELEGATION_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            context = get_surrounding_context(text, match.start(), match.end())

            # 除外パターンチェック
            if is_excluded(context):
                continue

            findings.append({
                "pattern": description,
                "matched": match.group(),
                "context": context.strip(),
            })

    return findings


def main():
    # stdinからhook入力JSONを読み取る
    try:
        raw_input = sys.stdin.read()
        if not raw_input.strip():
            sys.exit(0)
        hook_input = json.loads(raw_input)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    # block後の再実行時はスキップ（infinite loop防止）
    if hook_input.get("stop_hook_active"):
        sys.exit(0)

    # アシスタントメッセージを抽出
    assistant_message = extract_assistant_message(hook_input)
    if not assistant_message:
        sys.exit(0)

    # 丸投げパターン検出
    findings = detect_delegation(assistant_message)
    if not findings:
        sys.exit(0)

    # block JSON をstdoutに出力（セッション終了をブロックし、自己修正ターンを強制）
    matched_desc = ", ".join(f["pattern"] for f in findings)
    reason = (
        f"[SELF-TEST GATE BLOCKED] Delegation phrase detected: {matched_desc}. "
        "You MUST run the test/verification yourself via Bash/tools instead of asking the user. "
        "Only delegate if admin privileges or password entry is physically required. "
        "Remove the delegation text, execute the test yourself, and output results."
    )

    # プロジェクト種別を判定してスキルパスを注入する
    cwd = hook_input.get("cwd") or os.getcwd()
    skill_results = []
    try:
        _hooks_dir = os.path.dirname(os.path.abspath(__file__))
        if _hooks_dir not in sys.path:
            sys.path.insert(0, _hooks_dir)
        from project_classifier import classify_project_type

        skill_results = classify_project_type(cwd)
    except Exception:
        skill_results = []

    if skill_results:
        project_names = " / ".join(project_name for project_name, _ in skill_results)
        skill_paths = "\n".join(skill_path for _, skill_path in skill_results)
        reason += (
            f"\n\n適切なテストスキル（プロジェクト種別: {project_names}）:\n"
            f"{skill_paths}"
        )

    result = {"decision": "block", "reason": reason}
    json.dump(result, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
