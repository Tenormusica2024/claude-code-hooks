# スマートテストディスパッチ TODO

## 背景

`test-delegation-detector` (Stop hook) が「テスト丸投げ」を検出した際に、
単純 block → **実装プロジェクトの種類をエージェントが判断して最適なテストスキルへ自動ディスパッチ** する仕組みに進化させる。

参考: `hesreallyhim/awesome-claude-code` (★35.6k) のhooks/skillsカタログ

詳細設計: `rules/smart-test-dispatch-spec.md`

---

## フェーズ1: 設計

- [ ] プロジェクト種別分類ロジックの設計
  - [ ] 分類カテゴリの確定（フック/AIエージェント/Webアプリ/バックエンド）
  - [ ] 検出シグナルの定義（import文・依存パッケージ・ディレクトリ構造・CWD）
  - [ ] 分類方法の選定（ルールベース優先 → LLMフォールバック）
- [ ] ディスパッチテーブルの設計
  - [ ] プロジェクト種別 → スキル名 のマッピング確定
  - [ ] フォールバックスキル（汎用TDDガード）の定義
- [ ] アーキテクチャ決定
  - [ ] 既存 `completion-hook.py` の修正 vs 新規ディスパッチフック作成
  - [ ] スキル格納場所（`~/.claude/skills/` 配下 vs フックリポジトリ内）

---

## フェーズ2: プロジェクト種別分類モジュール

- [ ] `hooks/project_classifier.py` の作成
  - [ ] CWD・ファイル構造からシグナル抽出する `classify_project_type()` 実装
  - [ ] `hook_utils.py` への統合検討（共通ユーティリティとして切り出すか）
- [ ] 各種別の検出ロジック実装
  - [ ] フック/プラグイン種別（`hooks/`・`hook_utils`・スコアリングロジック検出）
  - [ ] AIエージェント種別（`agent`・`letta`・`openai`・`anthropic` import 検出）
  - [ ] Webアプリ種別（`playwright`・`cypress`・`auth`・`session` 検出）
  - [ ] バックエンドAPI種別（`fastapi`・`django`・`flask`・`APIRouter` 検出）
- [ ] 分類精度のテスト（pytest unit test）

---

## フェーズ3: テストスキル実装（`~/.claude/skills/` 配下）

- [ ] 汎用TDDガードスキル（`tdd-guard/SKILL.md`）
  - [ ] pytest ベースのテスト実行フロー定義
  - [ ] red → green → refactor サイクル強制ロジック
  - [ ] awesome-claude-code の TDD Guard 実装を参考に
- [ ] AIエージェントテストスキル（`agent-test/SKILL.md`）
  - [ ] promptfoo 統合パターン（declarative config → CI/CD）
  - [ ] LLM mocking（responses/httpretty）+ pytest-asyncio アプローチ
  - [ ] マルチエージェント integration test のひな形
- [ ] WebアプリE2Eテストスキル（`e2e-auth-test/SKILL.md`）
  - [ ] Playwright `storageState` による認証セッション保存・再利用パターン
  - [ ] ログイン → 操作 → 検証 のフルフローテンプレート
  - [ ] CI安定化のための tips（flaky回避・並列実行）
- [ ] バックエンドテストスキル（`backend-test/SKILL.md`）
  - [ ] FastAPI: `httpx.AsyncClient` + `ASGITransport` + `dependency_overrides` パターン
  - [ ] Django/Flask 対応
  - [ ] factory_boy/moto による外部依存モック

---

## フェーズ4: ディスパッチロジック組み込み

- [ ] `completion-hook.py` の修正
  - [ ] テスト block 発動時に `project_classifier.classify_project_type()` を呼び出す
  - [ ] 分類結果に応じたスキル名を `stopReason` or `additionalContext` に注入
  - [ ] 既存スコアリングロジックとの干渉確認
- [ ] `UserPromptSubmit` フックとの連携検討
  - [ ] プロジェクト種別をセッション全体でキャッシュする方法

---

## フェーズ5: テスト・ドキュメント整備

- [ ] 各スキルの動作確認（4カテゴリ × 実プロジェクトでの検証）
- [ ] `rules/hooks-spec.md` にディスパッチロジック仕様を追記
- [ ] `README.md` にスマートディスパッチフローを追記
- [ ] `install.ps1` への新スキルの追加手順を記載
- [ ] `tests/test_project_classifier.py` の作成

---

## 完了条件

- [ ] 4カテゴリのプロジェクトで正しいスキルが発動することを確認
- [ ] 既存フックの誤発火率が悪化していないことを確認
- [ ] ドキュメントが人間視点で読んで理解できる状態
