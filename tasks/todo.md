# スマートテストディスパッチ TODO

## 背景

`test-delegation-detector` (Stop hook) が「テスト丸投げ」を検出した際に、
単純 block → **実装プロジェクトの種類をエージェントが判断して最適なテストスキルへ自動ディスパッチ** する仕組みに進化させる。

参考: `hesreallyhim/awesome-claude-code` (★35.6k) のhooks/skillsカタログ

詳細設計: `rules/smart-test-dispatch-spec.md`

---

## フェーズ1: 設計

- [x] プロジェクト種別分類ロジックの設計
  - [x] 分類カテゴリの確定（フック/AIエージェント/Webアプリ/バックエンド）
  - [x] 検出シグナルの定義（import文・依存パッケージ・ディレクトリ構造・CWD）
  - [x] 分類方法の選定（ルールベース優先 → LLMフォールバック）
- [x] ディスパッチテーブルの設計
  - [x] プロジェクト種別 → スキル名 のマッピング確定
  - [x] フォールバックスキル（汎用TDDガード）の定義
- [x] アーキテクチャ決定
  - [x] 既存 `completion-hook.py` の修正 vs 新規ディスパッチフック作成
  - [x] スキル格納場所（`~/.claude/skills/` 配下 vs フックリポジトリ内）

---

## フェーズ2: プロジェクト種別分類モジュール

- [x] `hooks/project_classifier.py` の作成
  - [x] CWD・ファイル構造からシグナル抽出する `classify_project_type()` 実装
  - [x] `hook_utils.py` への統合検討（共通ユーティリティとして切り出すか）
- [x] 各種別の検出ロジック実装
  - [x] フック/プラグイン種別（`hooks/`・`hook_utils`・スコアリングロジック検出）
  - [x] AIエージェント種別（`agent`・`letta`・`openai`・`anthropic` import 検出）
  - [x] Webアプリ種別（`playwright`・`cypress`・`auth`・`session` 検出）
  - [x] バックエンドAPI種別（`fastapi`・`django`・`flask`・`APIRouter` 検出）
- [x] 分類精度のテスト（pytest unit test）

---

## フェーズ3: テストスキル実装（`~/.claude/skills/` 配下）

- [x] 汎用TDDガードスキル（`tdd-guard/SKILL.md`）
  - [x] pytest ベースのテスト実行フロー定義
  - [x] red → green → refactor サイクル強制ロジック
  - [x] フック固有: スコアリング境界値テスト・hook_utils モック・tmp_path パターン
- [x] AIエージェントテストスキル（`agent-test/SKILL.md`）
  - [x] promptfoo 統合パターン（declarative config → CI/CD）
  - [x] LLM mocking（responses/httpretty/unittest.mock）+ pytest-asyncio アプローチ
  - [x] マルチエージェント integration test のひな形
- [x] WebアプリE2Eテストスキル（`e2e-auth-test/SKILL.md`）
  - [x] Playwright `storageState` による認証セッション保存・再利用パターン
  - [x] ログイン → 操作 → 検証 のフルフローテンプレート（Node.js + Python 両対応）
  - [x] CI安定化のための tips（flaky回避・リトライ・スクリーンショット）
- [x] バックエンドテストスキル（`backend-test/SKILL.md`）
  - [x] FastAPI: `httpx.AsyncClient` + `ASGITransport` + `dependency_overrides` パターン
  - [x] Django/Flask 対応
  - [x] factory_boy/moto による外部依存モック

---

## フェーズ4: ディスパッチロジック組み込み

- [x] `test-delegation-detector.py` への統合（設計変更: completion-hook → test-delegation-detector）
  - [x] テスト block 発動時に `project_classifier.classify_project_type()` を呼び出す
  - [x] 分類結果に応じたスキルパスを block メッセージの reason に注入
  - [x] 既存スコアリングロジックとの干渉なし（block 確定後に追加情報として注入）
- [ ] （将来実装予定）`UserPromptSubmit` フックとの連携検討
  - [ ] プロジェクト種別をセッション全体でキャッシュし、複数フックから参照可能にする
  - [ ] 他フックからの参照ニーズが具体化した時点で着手

---

## フェーズ5: テスト・ドキュメント整備

- [x] 各スキルの動作確認（4カテゴリ × 実プロジェクトでの検証）
  - [x] claude-code-hooks → フック/プラグイン → tdd-guard
  - [x] ai_news_agent → AIエージェント(+Webアプリ同数) → agent-test + e2e-auth-test
  - [x] cafe_site → 汎用(静的サイトでシグナルなし) → tdd-guard
  - [x] ai-model-tracker-api → バックエンドAPI → backend-test
- [x] `README.md` にスマートディスパッチフロー・全6フック・テストスキル一覧を追記
- [x] `install.ps1` に全フック+project_classifier+テストスキルディレクトリのコピーを追加
- [x] `tests/test_project_classifier.py` の作成（7テスト全PASSED）

---

## 完了条件

- [x] 4カテゴリのプロジェクトで正しいスキルが発動することを確認
- [x] 既存フックの誤発火率が悪化していないことを確認
- [x] ドキュメントが人間視点で読んで理解できる状態
