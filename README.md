# claude-code-hooks

[![test](https://github.com/Tenormusica2024/claude-code-hooks/actions/workflows/test.yml/badge.svg?branch=master)](https://github.com/Tenormusica2024/claude-code-hooks/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)

Stop hooks and UserPromptSubmit hooks for **Claude Code quality guardrails**.
They block user-delegation, false completion, and low-signal workflow slips before they become bad habits in daily use.

**Good fit for** teams or solo operators who want Claude Code to test, review, and document changes more autonomously instead of pushing that judgment back to the user.

## What this repo covers

- block “please test/verify it yourself” style user-delegation
- block premature “done” messages when no real test evidence exists
- auto-route Claude toward the right test skill for the current project shape
- inject safer context when the user asks Claude to update docs such as `CLAUDE.md`

---

以下、日本語で詳細を説明します。

Claude Code の品質ガードレール用 Stop hooks / UserPromptSubmit hooks。
ユーザーへの確認委譲を検出して block し、Claude 自身に自己修正させる。
ドキュメント更新指示には追記コンテキストを注入する。

**Target environment:** currently optimized for **Windows + PowerShell + Claude Code local setup**.

fork / clone 後の最短導線は `docs/quickstart-from-fork.md` を参照。

## 収録フック

### test-delegation-detector.py
テスト・確認作業をユーザーに丸投げする行為を検出してblock。

**検出対象:**
- 「試してみてください」「確認してみてください」等
- 「手動で実行してください」
- 「ブラウザで開いてみてください」

**除外:** 管理者権限・ログイン認証・2FAが必要な場合

**スマートテストディスパッチ:** block時にCWDのプロジェクト種別を自動判定し、最適なテストスキルのパスをblockメッセージに注入する。Claudeがそのスキルを読んで自律的にテストを実行する。

> 注意: fresh fork 直後は dispatch 先 skill (`tdd-guard`, `agent-test`, `e2e-auth-test`, `backend-test`) の directory は作れても、`SKILL.md` 本体は別途用意が必要。

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

---

### document-update-detector.py（UserPromptSubmit hook）
「CLAUDE.mdを更新して」「マスタードキュメントを更新して」等の更新指示を検出し、対象ファイルをバックアップしてから用途別の更新コンテキストをClaudeに注入する。

**検出対象:**
- `CLAUDE.md` / `マスタードキュメント` への言及
- 引用パス (`"path/to/file.md"`) 形式の明示指定
- 更新・追記・記載・追加等のアクション語

**4つの注入モード（用途別にコンテキストが異なる）:**

| モード | 発火プロンプト例 | 注入コンテキストの特徴 |
|--------|-----------------|-----------------------|
| `claude` | `CLAUDE.md を更新して` | 70% 縮小・整合性チェック・古い情報削除を要求する更新コンテキスト |
| `claude_append` | `CLAUDE.md に追記して` | 追記専用。70% 縮小なし・既存内容の書き換え禁止 |
| `master` | `マスタードキュメントを更新して` | 既存フォーマット厳守の進捗更新コンテキスト（プロジェクト進捗管理向け） |
| `doc_smart` | `ドキュメントを更新して`（対象ファイル未指定） | 候補 `.md` を列挙して Claude に選ばせる。明示パス指定なしでも暴走しない |

**挙動:**
- 対象ファイルを `.bak` 接尾辞でバックアップ（`doc_smart` のみ Claude 側でバックアップを作る）
- `additionalContext` に Append-only 制約・品質チェックリスト・履歴書き込み指示を埋め込む
- `cwd` 欠損 / `stop_hook_active=true` では発火しない
- 「グローバル CLAUDE.md」指定時は `global-claude-md-appender.py` に処理を譲る（二重発火ガード）

### global-claude-md-appender.py（UserPromptSubmit hook）
グローバル CLAUDE.md (`~/.claude/CLAUDE.md`) 専用の肥大化ガード付き追記 hook。`Path.home()` ベースでマシン非依存。

**発火条件（AND）:**
- 「グローバルCLAUDE.md」または「グローバル CLAUDE.md」
- 「を更新して / に追記して / に記載して / に追加して」

**肥大化ガード:**
| 行数 | 警告レベル |
|------|-----------|
| 150行以上 | 推奨上限接近 → 外部ファイル参照優先 |
| 200行以上 | 強警告 → インライン記載を避ける |

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
    document-update-detector.py
    global-claude-md-appender.py
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

※ 正確には `install.ps1` は **skill directory を作るところまで** を担当し、`SKILL.md` 自体の配布・配置は別途必要。

## settings.json への登録

`install.ps1` は settings.json を自動パッチしない。**手動登録が必須**（登録しないとhookは発火しない）。

### Stop hooks

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

### UserPromptSubmit hooks

`~/.claude/settings.json` の `hooks.UserPromptSubmit` に追加:

```json
{
  "type": "command",
  "command": "python \"C:\\Users\\<USERNAME>\\.claude\\hooks\\document-update-detector.py\""
},
{
  "type": "command",
  "command": "python \"C:\\Users\\<USERNAME>\\.claude\\hooks\\global-claude-md-appender.py\""
}
```

### 登録確認

`install.ps1` は `hooks.UserPromptSubmit` 配下にhookファイル名が存在するかを個別にチェックし、登録漏れを表示する。登録後に再実行して確認すること。

## テスト実行

```bash
pytest tests/ -xvs
```
