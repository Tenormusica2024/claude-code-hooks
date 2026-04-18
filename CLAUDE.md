# claude-code-hooks

Claude Code品質ガードレール用 Stop hooks / UserPromptSubmit hooks のリポジトリ。

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
「CLAUDE.mdを更新して」「マスタードキュメントを更新して」等の更新指示を検出し、対象ファイルをバックアップして追記コンテキストを注入する。

**発火条件:**
- プロンプトに `CLAUDE.md` / `マスタードキュメント` / 引用パス (`"path/to/file.md"`) のいずれか
- かつ「更新」「追記」「記載」等のアクション語
- `cwd` が存在し `stop_hook_active=false` のときのみ発火

**挙動:**
- 対象ファイルを `.bak` としてバックアップ
- Claude へ「Append-only / 品質チェックリスト / 履歴書き込み」を含む `additionalContext` を返す

### global-claude-md-appender.py（UserPromptSubmit hook）
グローバル CLAUDE.md (`~/.claude/CLAUDE.md`) 専用の肥大化ガード付き追記 hook。

**発火条件:**
- プロンプトに「グローバルCLAUDE.md」または「グローバル CLAUDE.md」
- かつ「を更新して / に追記して / に記載して / に追加して」

**肥大化ガード:**
- 150行以上: 外部ファイル参照推奨の警告
- 200行以上: 強警告（インライン禁止推奨）

**配置:** `~/.claude/CLAUDE.md` を `Path.home()` ベースで参照するためマシン非依存。

---

## 📚 学んだ教訓

- [smart-test スキルのルーティング設計]: classifier が返す `skill=` パスをそのまま使う。ルーティングテーブルでキーを照合する設計は classifier 出力と型が合わずに宙に浮く → 正しいやり方は「classifier の出力を信頼してパスを直接読み込む。手動フォールバック時のみカウントベースの表を使う」
- [同点時の処理]: スキル内で「後述の〜セクションに従う」と参照先を書く前に、そのセクションが存在するか確認する。ない場合はインラインで記述するかセクションを追加する
