# フック仕様詳細
<!-- 目的: 各フックのスコアリング方式・トリガーワード・動作の詳細仕様 -->

## 用語定義

| 用語 | 意味 |
|------|------|
| **mutation tool** | ファイルを変更するツール（Edit / Write / MultiEdit）。コード実装が伴う操作の証拠として使用。 |
| **additionalContext** | UserPromptSubmit フックが stdout に出力する JSON。Claude の次のターンに自動注入される追加指示。 |
| **rfl** | `/review-fix-loop` スキルの略称。レビュー→自動修正→再レビューの反復ループ。 |
| **pending_issues.json** | 未解決の要確認事項を記録する JSON ファイル（`cwd/.claude/pending_issues.json`）。test-complete-hook のガード条件として参照される。 |
| **quoted path** | ASCII 引用符（`"..."` または `'...'`）で囲まれたファイルパス。document-update-detector がカスタムターゲットとして認識する。 |

---

## test-delegation-detector.py

テスト・確認作業をユーザーに丸投げしようとする応答を検出し、block する。

**スコアリング方式（v2）:** `score >= 5` で block
- +5: 「試してみてください」「確認してみてください」等の委譲フレーズを検出
- +4: 「〜してください」＋「テスト/確認/実行/チェック」の組み合わせ
- +3: アシスタントメッセージ末尾に委譲表現が集中している
- -5: mutation tool が現在ターンで使用されていない（実装を伴わない応答）
- -4: 除外パターン（コード例の中のコメント、引用符内の文字列等）

---

## claude-md-auto-recorder.py

「CLAUDE.md に書いておきますか？」等の確認委譲を block し、Claude 自身が記録/スキップを自律判断する。

**動作:**
1. 「CLAUDE.md に〜しますか」「記録しておきますか」等の確認委譲フレーズを検出
2. block して Claude に自律判断を促す指示を注入
3. Claude は記録すべきと判断した場合は確認なしで即座に記録、不要と判断した場合はスキップ

**スコアリング方式（v2）:** `score >= 5` で block
- +5: 確認委譲フレーズを検出（「しますか」「しておきますか」＋「記録/追記/書く/保存」）
- +3: アシスタントメッセージ末尾の疑問文
- -5: mutation tool が使用されていない（実装済み操作に対する確認ではない）
- -4: 除外パターン（ユーザーへの選択肢提示が主目的のメッセージ）

---

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

> ⚠️ `rules/design-decisions.md` は意図的にスキャン対象から除外する。設計根拠の記録は doc_smart の自動圧縮・書き換えから保護するため、更新する場合は対象パスを明示指定すること（例: `"rules/design-decisions.md" のマスタードキュメントを更新して`）。

**`merge_parallel_reviews.py` について:**
> ※ 外部ツール（本リポジトリに含まれない。`/rfl --parallel` / `/rfl --d` 等の並列レビューパイプラインと組み合わせて使用するローカル運用スクリプト）

**document-update-detector の出力フォーマット:**

**出力ラベル:**
- `[高信頼]`: 2モデル以上が同一指摘を検出した場合に付与（`detection_count >= 2`）。自動修正可・要確認の両セクションで表示される。

**exit code:**
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
