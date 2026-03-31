# -*- coding: utf-8 -*-
"""
claude-md-auto-recorder.py の回帰テスト
"""
import json
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).parent.parent / "hooks" / "claude-md-auto-recorder.py"


def run_hook(message: str) -> bool:
    payload = json.dumps({"last_assistant_message": message})
    result = subprocess.run(
        [sys.executable, str(HOOK)],
        input=payload.encode("utf-8"),
        capture_output=True,
    )
    output = result.stdout.decode("utf-8").strip()
    return bool(output and "block" in output)


SHOULD_BLOCK = [
    "CLAUDE.mdに残しておきますか？",
    "CLAUDE.mdへ記録しておきましょうか？",
    "プロジェクトのCLAUDE.mdに追記しておきますか？",
    "この教訓をCLAUDE.mdに書いておく？",
    "CLAUDE.mdに更新しておきますか？",
    "CLAUDE.mdに書いておきましょうか？",
    "CLAUDE.mdに保存しておきますか？",
]

SHOULD_PASS = [
    # 完了報告（書き込み済み）
    "CLAUDE.mdに追記しました。",
    "CLAUDE.mdに記録済みです。",
    # 参照・言及のみ
    "CLAUDE.mdを参照してください。",
    "CLAUDE.mdの内容を確認します。",
    # 読み取り文脈（false positive対象）
    "CLAUDE.mdに残してある設定を確認しますか？",
    # 引用テキスト内のパターン
    "「CLAUDE.mdに書いておく？」という質問行為自体をblockしたい",
    # 無関係なフレーズ
    "試してみてください",
]


def main():
    failures = 0
    for msg in SHOULD_BLOCK:
        if not run_hook(msg):
            print(f"[NG] should block: {msg}")
            failures += 1
        else:
            print(f"[OK] blocked: {msg}")

    for msg in SHOULD_PASS:
        if run_hook(msg):
            print(f"[NG] should pass: {msg}")
            failures += 1
        else:
            print(f"[OK] passed: {msg}")

    total = len(SHOULD_BLOCK) + len(SHOULD_PASS)
    print(f"\nResult: {total - failures}/{total} passed")
    return failures


if __name__ == "__main__":
    sys.exit(main())
