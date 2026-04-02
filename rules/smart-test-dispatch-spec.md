# スマートテストディスパッチ 設計仕様
<!-- 目的: テスト丸投げ検出→プロジェクト種別判定→最適スキル自動発動のアーキテクチャと設計決定を記録 -->

## 概要

既存の `test-delegation-detector` が「テスト丸投げ」を block するだけの防御的フックから、
**実装プロジェクトの種類をエージェントが判断して最適なテストスキルを自動発動する** 能動的なフックへ進化させる。

参考: `hesreallyhim/awesome-claude-code` (★35.6k) の hooks/skills カタログ

実装 TODO: `tasks/todo.md`

---

## フロー概略

```
Claude がテスト丸投げ発言
          ↓
[test-delegation-detector] 検出・block
          ↓
[completion-hook] → project_classifier でプロジェクト種別を判定
          ↓
     種別に応じてスキル名を additionalContext に注入
    ↙         ↓          ↘         ↘
tdd-guard  agent-test  e2e-auth   backend-test
（汎用）   （AIエージェント）（Webアプリ）（バックエンド）
```

スキルは 1 つに固定せず、エージェントが CWD のシグナルを読んで分岐する。

---

## プロジェクト種別と対応スキル

| 種別 | 検出シグナル（優先順） | スキル名 | 参考実装 |
|------|---------------------|---------|---------|
| フック/プラグイン | `hooks/`ディレクトリ・`hook_utils`・`score`・`block` 変数 | `tdd-guard` | pytest-dev/pluggy |
| AIエージェント | `agent`・`letta`・`openai`/`anthropic` import・`MCP`・`.claude/` | `agent-test` | promptfoo/promptfoo (★19k) |
| Webアプリ（ログイン込み） | `playwright`・`cypress`・`auth`・`session`・`cookie` | `e2e-auth-test` | microsoft/playwright |
| バックエンドAPI | `fastapi`・`django`・`flask`・`APIRouter`・`@app.route` | `backend-test` | zhanymkanov/fastapi-best-practices (★16.9k) |
| 汎用（フォールバック） | 上記以外 | `tdd-guard` | awesome-claude-code TDD Guard |

---

## 分類ロジック設計方針

### ルールベース分類（第1優先）

CWD の以下の情報から種別シグナルを抽出する:

1. **依存パッケージ**（`requirements.txt` / `pyproject.toml` / `package.json`）
2. **import 文**（変更対象ファイルの先頭 30 行をスキャン）
3. **ディレクトリ構造**（`hooks/`・`.claude/`・`tests/`・`app/`・`api/` の存在）
4. **ファイル名パターン**（`*_hook.py`・`*_agent.py`・`*.spec.ts` 等）

複数種別のシグナルが混在する場合は、検出シグナル数が最多の種別を選択する。

### LLM フォールバック（第2優先）

ルールベースで種別不明（スコア同数・シグナルなし）の場合、
`additionalContext` にプロジェクト種別の推定を Claude に依頼する一文を追加する。

---

## ディスパッチ実装方針

### 修正対象: `test-delegation-detector.py`（completion-hookではない）

新規フックを追加するのではなく、**既存の `test-delegation-detector.py` へ拡張**を選択する。

- 理由: 「丸投げ検出の直後にスキルを提示する」のが最も意図的に自然なタイミング
- completion-hookは「実装完了検出」の責務を保ったまま変更しない
- `project_classifier.py` を `hooks/` 配下に新規作成し、test-delegation-detector から呼び出す

### スキル発動メカニズム

blockメッセージ（または `additionalContext`）にスキルファイルのフルパスを注入する。
Claude がそのパスを読んで自律的に SKILL.md に従い実行する。

```python
# blockメッセージ内のスキルパス注入例
skill_paths = classify_and_get_skills(cwd)
skill_hint = "\n".join(f"- {p}" for p in skill_paths)
block_message += f"\n\n適切なテストスキル:\n{skill_hint}"
```

### 同数シグナル時の挙動

複数種別のシグナル数が同数の場合、**全スキルパスを注入**する。
Claude が順次適用するため、スキル間の優先順位テーブルは不要。

### ファイルスキャン方式

毎回ステートレスにスキャンする（セッション間キャッシュなし）。
hook 発火ごとのファイル読込コストは無視できるレベルのため。

### スキル格納場所

- スキルファイル本体は `~/.claude/skills/` 配下に配置（Claude Code が読み込む標準パス）
- このリポジトリには各スキルの **仕様テンプレート**（`skills-spec/` ディレクトリ）を管理

---

## 各スキルの責務

### tdd-guard（汎用TDDガード）

- pytest でテストを実行し、red → green → refactor サイクルを強制
- テスト未作成の場合はテストファイル作成を先に促す
- awesome-claude-code の TDD Guard 実装を参考に

### agent-test（AIエージェントテスト）

- `promptfoo` の declarative config でエージェントの挙動を eval
- pytest + `responses`/`httpretty` で LLM API 呼び出しをモック
- マルチエージェント連携: 各エージェントの tool call/output を snapshot/assert

### e2e-auth-test（Webアプリ E2E テスト）

- Playwright `storageState` で 1 回だけログイン → JSON 保存 → 全テストで再利用
- `.auth/` ディレクトリを `.gitignore` に追加するステップも含む
- CI 安定化: flaky 回避のための wait/retry 戦略を注入

### backend-test（バックエンドフレームワークテスト）

- FastAPI: `httpx.AsyncClient` + `ASGITransport` + `dependency_overrides`
- Django: `pytest-django` + `TestCase` + `factory_boy`
- Flask: `test_client()` + `pytest` fixtures

---

## 参考リポジトリ

| リポジトリ | Stars | 用途 |
|-----------|-------|------|
| hesreallyhim/awesome-claude-code | ★35.6k | TDD Guard, parry, hooks カタログ |
| promptfoo/promptfoo | ★19k | AIエージェントテスト・red teaming |
| microsoft/playwright | 数十万 | E2E 認証テスト標準 |
| zhanymkanov/fastapi-best-practices | ★16.9k | バックエンドテストパターン |
| pytest-dev/pluggy | 高評価 | フック/プラグインテストの基盤 |
| TheJambo/awesome-testing | ★2.2k | テスト全般の包括カタログ |
| cleder/awesome-python-testing | ★279 | Python 特化・LLM & MCP Testing 含む |
