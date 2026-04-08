# claude-code-hooks

Claude Code の品質ガードレール用 Stop hooks。
ユーザーへの確認委譲を検出してblockし、Claude自身に自己修正させる。

## 収録フック

### test-delegation-detector.py
テスト・確認作業をユーザーに丸投げする行為を検出してblock。

**検出対象:**
- 「試してみてください」「確認してみてください」等
- 「手動で実行してください」
- 「ブラウザで開いてみてください」

**除外:** 管理者権限・ログイン認証・2FAが必要な場合

**スマートテストディスパッチ:** block時にCWDのプロジェクト種別を自動判定し、最適なテストスキルのパスをblockメッセージに注入する。Claudeがそのスキルを読んで自律的にテストを実行する。

```
テスト丸投げ検出 → block
        |
  project_classifier.py でCWD解析
        |
   種別に応じてスキルパス注入
   /        |          \          \
tdd-guard  agent-test  e2e-auth-test  backend-test
```

| プロジェクト種別 | 検出シグナル | テストスキル |
|-----------------|------------|------------|
| フック/プラグイン | `hooks/`, `hook_utils`, `score=`, `block=` | `tdd-guard` |
| AIエージェント | `openai`/`anthropic` import, `agent`, `.claude/` | `agent-test` |
| Webアプリ | `playwright`/`cypress`, `auth`/`session`, `.spec.ts` | `e2e-auth-test` |
| バックエンドAPI | `fastapi`/`django`/`flask`, `APIRouter`, `@app.route` | `backend-test` |
| 汎用(フォールバック) | 上記以外 | `tdd-guard` |

---

### claude-md-auto-recorder.py
「CLAUDE.mdに書いておきますか？」系の確認をユーザーに委ねる行為を検出してblock。

**検出条件（AND）:**
1. `CLAUDE.md` への言及
2. 記録・追記・更新系のアクションワード
3. 質問・確認表現（？ / でしょうか / ますか 等）

**block後の挙動:** Claude自身が品質ゲートを判断して書くかスキップかを決定する。
- 再利用可能な教訓 → 書く
- 一回限りの細かい観察 → スキップ

---

### completion-hook.py
実装完了宣言を検出し、テスト未実行の場合にblockしてテスト実行を強制する。
スコアリング方式（v2）: `score >= 5` でblock。

---

### test-complete-hook.py
テスト完了を検出し、`/ifr --d` レビューパイプラインを自動発動する。
スコアリング方式（v2）: `score >= 6` でblock。

## 補助モジュール

### hooks/hook_utils.py
全フック共通のユーティリティ。transcript読み込み・ツール出力解析・テストフレームワーク検出・スコアリング補助などを提供する。

### hooks/project_classifier.py
CWDのファイル構造・依存パッケージ・importパターンからプロジェクト種別を判定するモジュール。
`test-delegation-detector.py` から呼び出される。

## ディレクトリ構成

```
claude-code-hooks/
  hooks/                    # フック本体 + 補助モジュール
    claude-md-auto-recorder.py
    completion-hook.py
    hook_utils.py
    project_classifier.py
    test-complete-hook.py
    test-delegation-detector.py
  rules/                    # 設計仕様・決定ログ
    design-decisions.md
    smart-test-dispatch-spec.md
  tests/                    # pytest テスト
    test_claude_md_recorder.py
    test_delegation_detector.py
    test_project_classifier.py
  tasks/                    # タスク管理
    todo.md
  install.ps1               # インストールスクリプト
  CLAUDE.md                 # Claude Code用プロジェクト指示
  README.md
```

## テストスキル（`~/.claude/skills/` 配下）

| スキル | 対象 |
|--------|------|
| `tdd-guard/SKILL.md` | pytest TDDガード + フック固有パターン |
| `agent-test/SKILL.md` | LLM APIモック + promptfoo eval |
| `e2e-auth-test/SKILL.md` | Playwright storageState認証 |
| `backend-test/SKILL.md` | FastAPI/Django/Flask テストクライアント |

## インストール

```powershell
.\install.ps1
```

`hooks/` 配下を丸ごと `~/.claude/hooks/` にコピーする（hook_utils.py は全フックの必須依存）。
テストスキルを `~/.claude/skills/` にコピーする。
settings.jsonへの登録は手動で行う（以下を参照）。

## settings.json への登録

`~/.claude/settings.json` の `hooks.Stop` に追加:

```json
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
```

## テスト実行

```bash
pytest tests/ -xvs
```
