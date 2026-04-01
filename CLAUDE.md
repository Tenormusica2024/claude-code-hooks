# claude-code-hooks

Claude Code 品質ガードレール用 Stop / UserPromptSubmit hooks のリポジトリ。

## 実装済みフック

| フック | 種別 | 機能 |
|--------|------|------|
| `test-delegation-detector.py` | Stop | 「試してみてください」等のテスト委譲を block |
| `claude-md-auto-recorder.py` | Stop | 確認委譲を block、Claude 自身が記録/スキップを判断 |
| `completion-hook.py` | Stop | 実装完了宣言を検出しテスト実行を強制（スコア >= 5） |
| `test-complete-hook.py` | Stop | テスト完了を検出し `/ifr --d` を自動発動（スコア >= 6） |
| `document-update-detector.py` | UserPromptSubmit | ドキュメント更新トリガーを検出し additionalContext を注入 |
| `global-claude-md-appender.py` | UserPromptSubmit | グローバル CLAUDE.md への追記トリガーを検出 |

**スコアリング詳細・トリガーワード仕様:** `rules/hooks-spec.md`

## 設計決定

**設計決定ログ:** `rules/design-decisions.md`
