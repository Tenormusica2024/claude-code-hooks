# フック仕様詳細
<!-- 目的: 各フックのスコアリング方式・トリガーワード・動作の詳細仕様 -->

## completion-hook.py

実装完了宣言を検出し、テスト未実行の場合に block してテスト実行を強制する。

**スコアリング方式（v2）:** `score >= 5` で block
- +5: Edit/Write/MultiEditが現在ターンで使用された
- +4: アシスタントメッセージの節に強い完了シグナル
- +3: 最後に使用したツールがmutation tool
- -6: 文法vetoパターン（「完了している理由」「完了条件」等）
- -5: mutation toolが使用されていない
- -4: 除外パターン（typo/コメント/README等）

---

## test-complete-hook.py

テスト完了を検出し、`/ifr --d` レビューパイプラインを自動発動する。

**スコアリング方式（v2）:** `score >= 6` で block
- +6: Bash出力にテストフレームワーク成功出力を検出（最強証拠）
- +4: Bash出力にテストコマンド実行の痕跡
- +3: MCP系テストツール使用
- +1: Bashツール使用（弱証拠。テスト無関係な Bash でも加点されるため低め設定）
- +3: アシスタントメッセージ内の節にテスト成功シグナル
- -5: ツール出力に失敗パターン
- -4: 「パス」がファイルパス文脈
- -3: テスト説明文脈

**guard条件:** `pending_issues.json` に未解決エントリがある場合はblockしない。

**2段パイプライン:**
```
実装完了報告
     ↓
[completion-hook] → テスト実行を強制
     ↓
テスト完了報告
     ↓
[test-complete-hook] → 要確認あり？ → STOP
                    → なし → /ifr --d 発動
```

---

## document-update-detector.py（UserPromptSubmit hook）

ユーザーの発言にドキュメント更新トリガーを検出し、Claude に additionalContext を注入してドキュメント更新を自動化する。

**トリガーワード:**
- `CLAUDE.md` ＋ 更新系アクション語 → cwd の CLAUDE.md を **70%縮小+整合性チェック付き** で更新
- `CLAUDE.md` ＋ 追記系アクション語 → cwd の CLAUDE.md を **追記のみ** で更新
- `マスタードキュメント` ＋ 書き込みアクション語 → master コンテキストで更新（quoted path があればそちらを優先）
- `ドキュメントを更新して` 等の省略形（quoted path なし） → `doc_smart`: 候補列挙 + Claude が選択 → 更新モード
- `ドキュメントに追記して` 等の省略形（quoted path なし） → `doc_smart_append`: 候補列挙 + Claude が選択 → 追記モード

**カスタムターゲットの指定:**
- ✅ `"path/to/master.md" のマスタードキュメントを更新して`（ASCII引用符必須）
- ❌ `path/to/master.md のマスタードキュメントを更新して`（引用符なし → 無視）

**動作:**
1. ターゲットが確定している場合（`claude` / `claude_append` / `master`）: フックがバックアップを作成
2. ターゲット未確定の場合（`doc_smart` / `doc_smart_append`）: Claude がターゲット選択後にバックアップを自ら作成
3. `cwd/.claude/updates/doc_update_history.md` に更新履歴を集約
4. `additionalContext` JSON を stdout に出力して Claude に更新手順を注入

**`doc_smart` / `doc_smart_append` の候補スキャン順:**
1. `cwd/CLAUDE.md`（プロジェクト全体のインデックス・軽量ルール）
2. `cwd/rules/*.md`（各ファイルの `<!-- 目的: ... -->` コメントを読んで説明を生成）

**`merge_parallel_reviews.py` の出力ラベル:**
- `[高信頼]`: 2モデル以上が同一指摘を検出した場合に付与（`detection_count >= 2`）。自動修正可・要確認の両セクションで表示される。

**`merge_parallel_reviews.py` の exit code:**
- `0`: 全モデル成功
- `1`: 全モデル失敗（エラー出力・ファイル未発見等）
- `2`: 部分失敗（一部モデルが非準拠出力・空出力。結果は出力されるが一部指摘が欠落している可能性あり）

**`doc_smart` 更新モードの圧縮ルール:**
- `CLAUDE.md` が選択された場合のみ 70% トークン縮小を適用
- `rules/*.md` が選択された場合は縮小なし（整合性チェック・陳腐化修正のみ）

---

## global-claude-md-appender.py（UserPromptSubmit hook）

グローバル CLAUDE.md（`~/.claude/CLAUDE.md`）への追記トリガーを検出し、追記専用の additionalContext を注入する。

**トリガーワード:** `グローバルCLAUDE.md` ＋ 更新系アクション語

**追記モードの制約:**
- 追記のみ（削除・リライト・整合性チェックなし）
- 70%縮小ルールなし
- 短く要点のみ

**v2 追加機能:**
- 行数モニタリング（150/200行超で警告）
- 品質チェックリスト注入
- 完了時の行数報告
