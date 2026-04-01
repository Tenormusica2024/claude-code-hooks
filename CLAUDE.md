# claude-code-hooks

Claude Code品質ガードレール用 Stop hooks のリポジトリ。

## 実装済みフック

### test-delegation-detector.py
「試してみてください」等のテスト委譲をblock。ユーザーへの丸投げを防ぎ自己実行を強制する。

### claude-md-auto-recorder.py
「CLAUDE.mdに書いておきますか？」等の確認委譲をblock。
品質ゲートをblockメッセージに埋め込み、Claude自身が記録/スキップを判断する。

---

### completion-hook.py
実装完了宣言を検出し、テスト未実行の場合にblockしてテスト実行を強制する。

**スコアリング方式（v2）:** `score >= 5` でblock
- +5: Edit/Write/MultiEditが現在ターンで使用された
- +4: アシスタントメッセージの節に強い完了シグナル
- +3: 最後に使用したツールがmutation tool
- -6: 文法vetoパターン（「完了している理由」「完了条件」等）
- -5: mutation toolが使用されていない
- -4: 除外パターン（typo/コメント/README等）

---

### test-complete-hook.py
テスト完了を検出し、`/ifr --d` レビューパイプラインを自動発動する。

**スコアリング方式（v2）:** `score >= 6` でblock
- +6: Bash出力にテストフレームワーク成功出力を検出（最強証拠）
- +4: Bash出力にテストコマンド実行の痕跡
- +3: MCP系テストツール使用
- +2: Bashツール使用
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

### document-update-detector.py（UserPromptSubmit hook）

ユーザーの発言にドキュメント更新トリガーを検出し、Claudeにadditionalcontextを注入してドキュメント更新を自動化する。

**トリガーワード:**
- `Claude.md` / `CLAUDE.md` ＋ 書き込みアクション語（を更新して/に追記して/に記載して/に追加して/に反映して/を修正して） → cwdのCLAUDE.mdを更新（読み取り指示のみでは発火しない）
- `マスタードキュメント` → master コンテキスト（プロジェクト進捗更新）で cwd/CLAUDE.md を更新。プロンプト内に別の明示パス（ASCII引用符で囲んだ .md パス・CLAUDE.md 以外）があればそちらを優先

**カスタムターゲットの指定方法（CLAUDE.md・マスタードキュメント 共通）:**
- ✅ `"path/to/master.md" のマスタードキュメントを更新して`（ASCII引用符必須）
- ✅ `"path/to/other.md" にCLAUDE.mdの内容を移植して`（CLAUDE.md トリガーでも quoted path が効く）
- ❌ `path/to/master.md のマスタードキュメントを更新して`（引用符なし → 無視）
- ❌ `'notes.md' を参考にマスタードキュメントを更新して`（参照文脈の quoted path → 無視）

**動作:**
1. トリガー検出時、対象ファイルの `.bak` バックアップを作成（タイムスタンプ+マイクロ秒で一意化）
2. `cwd/.claude/updates/doc_update_history.md` に更新履歴を集約（対象ファイルの場所に関わらず常に cwd 基準）
3. `additionalContext` JSONをstdoutに出力してClaudeに更新手順を注入

**優先順位:** 両方のトリガーワードを含むプロンプトでは、`マスタードキュメント` を優先して評価する

---

### global-claude-md-appender.py（UserPromptSubmit hook）

ユーザーの発言にグローバル CLAUDE.md への追記トリガーを検出し、追記専用の additionalContext を注入する。

**トリガーワード:** `グローバルCLAUDE.md`（または `グローバルClaude.md`）＋以下のいずれか
- `を更新して`
- `に追記して`
- `に記載して`
- `に追加して`

**対象ファイル:** `C:\Users\Tenormusica\.claude\CLAUDE.md`（固定・引数なし）

**動作:**
1. トリガー検出時、対象ファイルの `.bak` バックアップを作成（タイムスタンプ+マイクロ秒で一意化）
2. `~/.claude/updates/doc_update_history.md` に更新履歴を集約
3. `additionalContext` JSONをstdoutに出力してClaudeに追記手順を注入

**追記モードの制約（document-update-detectorとの違い）:**
- **追記のみ** — 既存コンテンツの削除・リライト・整合性チェックは行わない
- **70%縮小ルールなし** — グローバル CLAUDE.md はユーザー確認なしで大幅変更しない
- **短く要点のみ** — 追記内容は "なるべく短く要点のみで言語化する" ガイドラインに従う

**v2 追加機能（hook v2）:**
- **行数モニタリング** — 追記前にファイル行数を読み込み、150行超・200行超で警告を表示（ブロックなし）
- **品質チェックリスト注入** — 「これがなかったら間違えるか？」「詳細は外部ファイルに分けられるか？」等のセルフチェックをadditionalContextに含める
- **推奨フォーマット例** — 短い箇条書き形式と外部参照パターン（`詳細: path/to/file.md`）を例示
- **完了時の行数報告** — 追記後の最終行数をレポートするよう指示を注入
