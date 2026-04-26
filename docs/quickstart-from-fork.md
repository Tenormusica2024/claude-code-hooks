# Quickstart from Fork

この文書は、`claude-code-hooks` を **fork / clone した直後に最短で価値確認するための導線**。

目的は:

1. `install.ps1` を実行する
2. `settings.json` に hook を登録する
3. 1 本だけ block 動作を確認する

完全セットアップではなく、**最初の成功体験** を作るための quickstart。

---

## 前提

- Windows
- PowerShell
- Claude Code ローカル環境
- `~/.claude/settings.json` を編集できる
- Python 3.10 / 3.11 / 3.12 のいずれか（CI もこの範囲で検証）

> 重要: この repo は現在 **Windows / PowerShell / Claude Code ローカル運用** を主対象にしている。  
> fresh fork 直後は Codex-only / non-Windows ユーザー向けの即時セットアップ導線は弱い。

---

## 先に知っておくべきこと

### 1. `install.ps1` は hook ファイルを入れる

これはすぐ使える。

### 2. テスト skill は自動で完成しない

`install.ps1` は次の directory を作るが:

- `tdd-guard`
- `agent-test`
- `e2e-auth-test`
- `backend-test`

**`SKILL.md` 自体は自動配置しない**。  
つまり smart test dispatch を完全再現したい場合は、対応 skill を別途用意する必要がある。

この quickstart では、まず **hook の block 自体が動くこと** を確認する。

---

## 最短手順

### 1. clone

```powershell
git clone https://github.com/Tenormusica2024/claude-code-hooks.git
cd claude-code-hooks
```

### 2. install

```powershell
.\install.ps1
```

### 3. `settings.json` に hook を登録

少なくとも quickstart では `Stop` にこれを入れる:

```json
{
  "type": "command",
  "command": "python \"C:\\Users\\<USERNAME>\\.claude\\hooks\\test-delegation-detector.py\""
}
```

必要なら README の `settings.json への登録` セクションにある他 hook も追加する。

### 4. block 動作を確認

Claude Code で、たとえば次のような応答が出る状況を作る:

- 「ブラウザで開いて確認してください」
- 「手動で実行してください」
- 「試してみてください」

期待:
- `test-delegation-detector.py` が block
- ユーザー丸投げを止める

### 5. local validation も 1 回通す

hook block の確認だけでなく、repo 自体の confidence を作るために CI と同じテストをローカルで 1 回回すとよい。

```powershell
pytest tests/ -xvs
```

この validation が通れば:

- hook 本体の Python surface が壊れていない
- `project_classifier.py` / `hook_utils.py` の基本挙動が壊れていない
- fresh fork 直後の変更有無を判断しやすい

---

## 次の段階

この quickstart が通ったら:

1. `claude-md-auto-recorder.py`
2. `completion-hook.py`
3. `test-complete-hook.py`
4. `document-update-detector.py`

の順で広げると理解しやすい。

---

## いまの制約

- PowerShell / Windows 前提
- `settings.json` の patch は手動
- smart test dispatch 先 skill は別途必要

特に最後の点が重要で、quickstart で最初に確認できるのは **hook block 自体**。  
dispatch の完全再現には `tdd-guard` / `agent-test` / `e2e-auth-test` / `backend-test` の `SKILL.md` を別途配置する必要がある。

つまり現状は:

> **pinned repo としては強いが、fresh fork で完全再現するにはまだ少し手作業がいる**

という状態。
