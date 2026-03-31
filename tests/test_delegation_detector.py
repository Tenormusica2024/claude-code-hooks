# -*- coding: utf-8 -*-
"""
test-delegation-detector.py の回帰テスト
"""
import json
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).parent.parent / "hooks" / "test-delegation-detector.py"


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
    "試してみてください",
    "テストしてみてください",
    "確認してみてください",
    "実行してみてください",
    "動作確認してみてください",
    "手動で実行してください",
    "ブラウザで開いてみてください",
    "以下のコマンドを実行してみてください",
]

SHOULD_PASS = [
    "管理者として実行してみてください",
    "ログインしてから確認してみてください",
    "テストが完了しました",
    "動作確認の結果、正常に動作しています",
    "2FAが必要なため確認してみてください",
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
