# claude-code-hooks

Claude Code の品質ガードレール用 Stop / UserPromptSubmit hooks。

「テストしてみてください」「実装が完了しました」をそのまま流さず、Claude 自身にテスト実行・レビュー起動・ドキュメント更新まで完遂させるフック群。

## 解決する問題

| よくある問題 | このフックがすること |
|---|---|
| Claude がテストをユーザーに丸投げする | `test-delegation-detector` が検出して block |
| 実装完了を宣言してもテストを走らせない | `completion-hook` がテスト実行を強制 |
| テスト後にレビューを依頼しない | `test-complete-hook` が自動でレビューパイプラインを起動 |
| 「CLAUDE.md に書いておきますか？」と聞いてくる | `claude-md-auto-recorder` が自律判断して記録 |
| ドキュメント更新を忘れる | `document-update-detector` がトリガーを検出して自動注入 |

## 収録フック

| フック | 種別 | 機能 | テスト |
|--------|------|------|--------|
| `test-delegation-detector.py` | Stop | 「試してみてください」等のテスト委譲を block | ✓ |
| `claude-md-auto-recorder.py` | Stop | 確認委譲を block、Claude 自身が記録/スキップを判断 | ✓ |
| `completion-hook.py` | Stop | 実装完了宣言を検出しテスト実行を強制（スコア >= 5） | 手動 |
| `test-complete-hook.py` | Stop | テスト完了を検出し `/ifr --d` を自動発動（スコア >= 6） | 手動 |
| `document-update-detector.py` | UserPromptSubmit | ドキュメント更新トリガーを検出し additionalContext を注入 | 手動 |
| `global-claude-md-appender.py` | UserPromptSubmit | グローバル CLAUDE.md への追記トリガーを検出 | 手動 |

スコアリング方式・トリガーワードの詳細: [`rules/hooks-spec.md`](rules/hooks-spec.md)

## フロー概略

```
実装完了宣言
    ↓
[completion-hook] テスト実行を強制
    ↓
テスト完了
    ↓
[test-complete-hook] /ifr --d レビューパイプライン起動
```

ユーザーがプロンプトに「CLAUDE.md を更新して」と書くだけでドキュメント更新も自動化される（`document-update-detector` が context を自動注入）。

## 前提条件

- Claude Code がインストール済み（hooks 機能が利用可能なバージョン）
- Python 3.10 以上
- インストール例は Windows パスで記載（macOS/Linux は適宜読み替え）

## インストール

```powershell
.\install.ps1
```

`hooks/` 配下の Stop hooks 4 本を `~/.claude/hooks/` にコピーする。
settings.json への登録は手動で行う（各ユーザーの既存設定を上書きしないため）。

## settings.json への登録

`~/.claude/settings.json` の `hooks` セクションに追加:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python \"C:\\Users\\<USERNAME>\\.claude\\hooks\\test-delegation-detector.py\""
          },
          {
            "type": "command",
            "command": "python \"C:\\Users\\<USERNAME>\\.claude\\hooks\\claude-md-auto-recorder.py\""
          },
          {
            "type": "command",
            "command": "python \"C:\\Users\\<USERNAME>\\.claude\\hooks\\completion-hook.py\""
          },
          {
            "type": "command",
            "command": "python \"C:\\Users\\<USERNAME>\\.claude\\hooks\\test-complete-hook.py\""
          }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python \"C:\\Users\\<USERNAME>\\.claude\\hooks\\document-update-detector.py\""
          },
          {
            "type": "command",
            "command": "python \"C:\\Users\\<USERNAME>\\.claude\\hooks\\global-claude-md-appender.py\""
          }
        ]
      }
    ]
  }
}
```

## アーキテクチャ

```
hooks/
├── hook_utils.py              # 共通ユーティリティ（UTF-8 I/O・ペイロード解析・スコアリング基盤）
├── test-delegation-detector.py
├── claude-md-auto-recorder.py
├── completion-hook.py
├── test-complete-hook.py
├── document-update-detector.py
└── global-claude-md-appender.py
```

`hook_utils.py` は全フックが共有するライブラリ。Windows の stdin/stdout UTF-8 設定・Claude Code からのペイロード解析・スコアリングロジックの共通基盤を提供する。

## テスト実行

```bash
python tests/test_delegation_detector.py
python tests/test_claude_md_recorder.py
```

`completion-hook` / `test-complete-hook` / `document-update-detector` / `global-claude-md-appender` は現時点で自動テストなし（手動検証で運用中）。
