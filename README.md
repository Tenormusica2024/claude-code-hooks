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

## インストール

```powershell
.\install.ps1
```

hookファイルを `~/.claude/hooks/` にコピーする。
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
}
```

## テスト実行

```bash
python tests/test_delegation_detector.py
python tests/test_claude_md_recorder.py
```
