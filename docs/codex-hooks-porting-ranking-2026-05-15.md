# Codex に移植したい Claude Code hooks ランキング（2026-05-15）

## 0. 前提

対象は主に `C:\Users\Tenormusica\claude-code-hooks` repo の Claude Code 向け hooks です。あわせて、実運用中の `C:\Users\Tenormusica\.claude\hooks` にある関連 hooks も「Codex に入れるなら欲しい機能」として補足評価しました。

現状の Codex CLI は `@openai/codex 0.130.0` / `hooks = stable true` なので、基本的な hook 移植は可能です。ただし Codex 側で確実に使いやすいのは次の範囲です。

- `SessionStart`
- `UserPromptSubmit`
- `PreToolUse`
- `PermissionRequest`
- `PostToolUse`
- `Stop`

一方で、Codex は Claude Code ほど `Read` / `Glob` / `WebSearch` / `FileChanged` / `PreCompact` / `SessionEnd` / `SubagentStart` などを広く拾えません。したがって、**Stop / UserPromptSubmit / Bash系PreToolUse に寄せた hook から入れるのが安全**です。

調査確認:
- `claude-code-hooks` repo は clean 状態。
- repo 内テストは `pytest tests -q` で `7 passed`。
- 公式参照: OpenAI Codex hooks docs / config reference、Claude Code hooks reference。

---

## 1. 結論ランキング：まず Codex に移植したい hooks

### 1位: `test-delegation-detector.py`

**Codex移植適性: A+**  
**欲しい度: 最高**  
**Codex event: `Stop`**

これは最優先です。理由は、ユーザーに「試してみてください」「確認してください」「ブラウザで見てください」と丸投げする問題を止める hook で、Codex でも同じ事故が起きやすいからです。

Codex の `Stop` hook は `decision: "block"` で終了を止め、理由文を次の継続 prompt として使えるので、この hook の思想と相性が良いです。`last_assistant_message` / `transcript_path` / `cwd` も Codex 側にあるため、基本設計はかなり流用できます。

**Codex 向けに変える点:**
- Claude Code の skill path 注入を Codex skill 名に置き換える。
  - `tdd-guard` → `sc-tdd`
  - `agent-test` → `sc-at`
  - `e2e-auth-test` → `sc-e2e`
  - `backend-test` → `sc-bt`
- transcript parser は Claude Code 前提なので、まずは `last_assistant_message` 優先にする。
- block message は Codex でも短く明確にする。

**クライアント向け説明:**
> AIが「ユーザー側で確認してください」と言って作業を終えるのを防ぐ安全装置です。Codex でも最初に入れる価値が高いです。

---

### 2位: `completion-hook.py`

**Codex移植適性: A**  
**欲しい度: 最高**  
**Codex event: `Stop`**

「実装完了」と言っているのにテスト・検証が走っていない場合に止める hook です。Codex でも非常に欲しいです。特に Codex は実装速度が高い分、「確認したように見えるが実際のテストは未実行」という事故を防ぐ効果があります。

**Codex 向けに変える点:**
- transcript 内の tool_use / tool_result 形式が Claude Code と違う可能性があるので、parser を Codex transcript に合わせて堅牢化する。
- 最初は「last assistant message が完了宣言っぽい」かつ「直近 turn に Bash / test 証跡がない」程度の軽量判定でよい。
- `pytest`, `npm test`, `pnpm test`, `go test`, `cargo test`, `curl`, screenshot smoke などをプロジェクト種別で案内する。

**クライアント向け説明:**
> Codex が実装完了と言った時に、テストや動作確認がないまま完了扱いにしないための品質ゲートです。

---

### 3位: `document-update-detector.py`

**Codex移植適性: A**  
**欲しい度: 高**  
**Codex event: `UserPromptSubmit`**

「CLAUDE.mdを更新して」「ドキュメントを更新して」系の依頼を検知して、バックアップと更新方針を追加 context として入れる hook です。Codex でも `UserPromptSubmit` は使えるので相性が良いです。

このユーザー環境では、source-of-truth を軽く保つこと、古い情報を残しすぎないこと、agent-friendly に構造化することが重要なので、かなり欲しい機能です。

**Codex 向けに変える点:**
- `CLAUDE.md` だけでなく、Codex で使う対象を明示する。
  - repo: `CODEX.md`, `AGENTS.md`, `CLAUDE.md`
  - global: `C:\Users\Tenormusica\CLAUDE.md`
  - Codex adapter: `C:\Users\Tenormusica\.codex\claude.md`
- 自動追記より「バックアップ作成 + 追記候補 + どこへ書くべきか」の context 注入に寄せる。
- `doc_smart` は Codex でも有効。対象ファイル未指定時に候補を出して暴走を防げる。

**クライアント向け説明:**
> ドキュメント更新依頼をAIに雑に処理させず、どのファイルへ、どの粒度で、古い情報をどう扱うかを自動で補助する hook です。

---

### 4位: `block-dangerous-git.sh`（repo収録外だが実運用中）

**Codex移植適性: A+**  
**欲しい度: 高**  
**Codex event: `PreToolUse` / matcher `Bash`**

これは `claude-code-hooks` repo 収録外ですが、Codex に入れるならかなり欲しいです。`git reset --hard`, `git clean`, 危険な force 操作などを Bash 実行前に止める用途です。

Codex の `PreToolUse` は Bash を捕まえられるので相性がよく、実装も軽いです。Claude Code 版の `decision: approve` のような pass 出力は Codex では不要なので、通常時は何も出さず exit 0、ブロック時だけ Codex 形式の deny / exit 2 にするのが良いです。

**クライアント向け説明:**
> AIがローカル作業中に破壊的な git 操作を実行する事故を防ぐガードです。導入コストに対する安全効果が大きいです。

---

### 5位: `global-claude-md-appender.py`

**Codex移植適性: B+**  
**欲しい度: 中〜高**  
**Codex event: `UserPromptSubmit`**

グローバル `CLAUDE.md` への追記を肥大化ガード付きで扱う hook です。Codex でも役に立ちますが、グローバル指示ファイルは全セッションに影響するため、Claude Code 版よりさらに慎重にした方が良いです。

**Codex 向けに変える点:**
- 直接 append より、まずは「追記候補を出す」「外部ルールファイル参照を提案する」に寄せる。
- Codex では `C:\Users\Tenormusica\.codex\claude.md` が軽量 adapter なので、むやみに肥大化させない。
- 本体 source-of-truth は `C:\Users\Tenormusica\CLAUDE.md` 側という前提を壊さない。

**クライアント向け説明:**
> グローバル運用ルールへの追記を雑に増やさないための肥大化ガードです。ただし影響範囲が大きいので、最初は提案型にした方が安全です。

---

### 6位: `claude-md-auto-recorder.py`

**Codex移植適性: B+**  
**欲しい度: 中**  
**Codex event: `Stop`**

「CLAUDE.mdに書いておきますか？」のように、AIが記録判断をユーザーへ丸投げするのを止める hook です。思想は良いですが、Codex では `document-update-detector.py` と役割が少し重なります。

**Codex 向けに変える点:**
- `CLAUDE.md` 固定ではなく、`CODEX.md` / `AGENTS.md` / `CLAUDE.md` / `.codex/claude.md` のどれが適切かを判断させる。
- 重要度が低いものは「書かない」と判断させる。
- いきなりファイル更新まで強制せず、最初は「記録するなら候補を作る」くらいでもよい。

**クライアント向け説明:**
> AIが記録判断をユーザーへ投げず、自分で再利用価値を判断するための hook です。便利ですが、文書更新系 hook と統合してもよいです。

---

### 7位: `test-complete-hook.py`

**Codex移植適性: B**  
**欲しい度: 中**  
**Codex event: `Stop`**

Claude Code 版では「テスト完了を検知したら `/ifr --d` レビューパイプラインへ進ませる」hook です。発想は良いですが、Codex には Claude Code の `/ifr --d` がそのままありません。Codex 側では `sc-ifr`, `sc-rfl`, `sc-gr` などの skill へ置き換える必要があります。

**Codex 向けに変える点:**
- `/ifr --d` ではなく、Codex skill の `sc-ifr` または `sc-rfl` を案内する。
- 自動 review はコストとループリスクがあるため、最初は「テスト完了後、差分が大きい場合だけ review を促す」程度にする。
- 完全自動 review loop は後回し。

**クライアント向け説明:**
> テスト後にレビューまで自動で進める hook です。価値はありますが、Codex ではレビューskill体系へ置き換える必要があるため、初期導入では後回しでよいです。

---

## 2. repo内の補助モジュール評価

### `hook_utils.py`

**移植必須度: 高**

`completion-hook.py` / `test-complete-hook.py` / document系 hook の共通処理です。Codex 移植では、そのままコピーするより `codex_hook_utils.py` のように分け、Codex transcript の差異を吸収する層にした方がよいです。

特に重要な関数:
- transcript 読み込み
- assistant message 抽出
- tool output / test command 検出
- bool flag parsing
- backup / additionalContext 出力

### `project_classifier.py`

**移植必須度: 高**

`test-delegation-detector.py` の smart test dispatch に必要です。これは Codex でもかなり有用です。Codex skill 名へ mapping するだけで価値が出ます。

置き換え候補:
- hook/plugin → `sc-tdd`
- AI agent → `sc-at`
- web app / auth E2E → `sc-e2e`
- backend API → `sc-bt`
- fallback → `sc-tdd`

---

## 3. 実運用 hooks から Codex に欲しい追加候補

`claude-code-hooks` repo には入っていないものの、現在 `~/.claude/hooks` にあり、Codex へ入れる価値が高いものです。

### 追加候補A: `block-flash-scheduler.py`

**Codex移植適性: A**  
**欲しい度: 高（Windows運用では特に）**  
**Codex event: `PreToolUse` / matcher `Bash`**

Task Scheduler 登録時に `python.exe` / `powershell.exe` / `.bat` 直実行でウィンドウフラッシュが起きる問題を防ぐ hook です。ユーザー環境は Windows + Task Scheduler 運用が多いので、かなり実用的です。

### 追加候補B: `ensure-ps1-bom.py`

**Codex移植適性: B+**  
**欲しい度: 中〜高**  
**Codex event: `PostToolUse` / matcher `apply_patch`**

PowerShell 5.1 が BOMなしUTF-8を誤読する問題を防ぐ hook です。Codex では file edit が `apply_patch` として来るため、patch から `.ps1` / `.psm1` / `.psd1` の変更ファイルを抽出する адапタが必要です。Windows自動化では価値があります。

### 追加候補C: `enforce-go-robust-submit.py` + `enforce-go-robust-stop.py`

**Codex移植適性: B**  
**欲しい度: 中〜高**

レビュー後の「要確認」を未処理のまま返さない hook です。これはユーザーの `go-robust` 運用と相性が良いですが、Claude Code の `/ifr`, `/rfl`, `/go-robust` コマンド体系に依存しています。Codex では `sc-ifr`, `sc-rfl`, `sc-gr` に置き換える必要があります。

### 追加候補D: `stop-hook-runner.js`

**Codex移植適性: B+**  
**欲しい度: 中**

Windows で複数 Stop hook を直接起動するとプロセス/ウィンドウ問題が出やすいので、runner でまとめる発想は Codex でも有効です。ただし、Codex 側は最初から hooks を増やしすぎない方がよいため、Phase 2 以降で十分です。

---

## 4. Codex には今は向かない / 後回しの hooks

### `block-websearch.py`

Codex の hooks は現時点で WebSearch を PreToolUse で確実に捕まえる前提にしない方がよいです。Codex docs でも WebSearch 等の non-shell / non-MCP tool call は hook interception 対象外とされています。これは hook ではなく Codex の `web_search` config / rules / prompt で制御する方が現実的です。

### `image-read-sonnet.py`

Claude Code の `Read` tool 前提です。Codex hooks では Read/画像読み取りを同じ形で捕まえにくいため、移植優先度は低いです。モデル分担は hook ではなく、運用ルールか skill 側で制御する方がよいです。

### `block-redundant-reads.py`

Read / Glob hook 前提なので Codex では今の hooks 範囲と合いません。Codex でやるなら、hook ではなく transcript 分析や Stop hook の「重複読みが多い」警告に変える必要があります。

### `strategic-compact.py`

Claude Code の tool count / compact 運用に寄った hook です。Codex には compaction 周辺 hook が Claude Code ほど揃っていないため、今は後回しでよいです。

---

## 5. 導入ロードマップ案

### Phase 1: 最小で効果が出る安全・品質 gate

1. `test-delegation-detector.py` の Codex版
2. `completion-hook.py` の Codex版
3. `block-dangerous-git.sh` の Codex版

この3つで、次を防げます。

- ユーザーへの確認丸投げ
- テスト未実行の完了宣言
- 破壊的 git 操作

最初の Codex hooks として一番コスパが良いです。

### Phase 2: ドキュメント運用 gate

4. `document-update-detector.py` の Codex版
5. `global-claude-md-appender.py` の提案型 Codex版
6. `claude-md-auto-recorder.py` の文書更新統合版

ここで、Codex / Claude 共有ルール、repo `CODEX.md` / `AGENTS.md` / `CLAUDE.md` の肥大化防止、バックアップ、追記判断を整えます。

### Phase 3: Windows運用・レビュー運用の強化

7. `block-flash-scheduler.py`
8. `ensure-ps1-bom.py`
9. `enforce-go-robust` の Codex skill 対応版
10. `test-complete-hook.py` の `sc-ifr` / `sc-rfl` 対応版

ここは有用ですが、初期導入で一気に入れると false positive やループの切り分けが難しくなります。

---

## 6. 最終ランキング表

| Rank | Hook / 機能 | Codex向き | 欲しい度 | 初期導入 | 理由 |
| --- | --- | --- | --- | --- | --- |
| 1 | `test-delegation-detector.py` | A+ | 最高 | P0 | ユーザー確認丸投げを防ぐ。Codex Stop hook と相性が良い |
| 2 | `completion-hook.py` | A | 最高 | P0 | テスト未実行の完了宣言を防ぐ。品質効果が大きい |
| 3 | `block-dangerous-git.sh` | A+ | 高 | P0 | Bash PreToolUse で破壊的 git を止められる。安全効果が大きい |
| 4 | `document-update-detector.py` | A | 高 | P1 | ドキュメント更新の暴走・肥大化を防げる |
| 5 | `block-flash-scheduler.py` | A | 高 | P2 | Windows Task Scheduler 運用では効果が大きい |
| 6 | `global-claude-md-appender.py` | B+ | 中〜高 | P1 | グローバルルール肥大化を抑える。ただし提案型が安全 |
| 7 | `ensure-ps1-bom.py` | B+ | 中〜高 | P2 | Windows PowerShell 5.1 事故を防ぐ。patch解析が必要 |
| 8 | `claude-md-auto-recorder.py` | B+ | 中 | P1 | 記録判断の丸投げ防止。document-update と統合がよい |
| 9 | `enforce-go-robust-*` | B | 中〜高 | P2 | レビュー要確認の放置防止。Codex skill 対応が必要 |
| 10 | `test-complete-hook.py` | B | 中 | P2 | テスト後レビュー誘導。Claude `/ifr` 依存を置き換える必要あり |
| 11 | `stop-hook-runner.js` | B+ | 中 | P2 | Windowsで複数hook運用する基盤。hooksが増えてからでよい |
| 12 | `block-websearch.py` | C | 低 | 後回し | Codex hooks では WebSearch を確実に捕まえにくい |
| 13 | `image-read-sonnet.py` | C | 低 | 後回し | Claude Code Read tool 前提。Codexでは別経路がよい |
| 14 | `block-redundant-reads.py` | C | 低 | 後回し | Read/Glob hook 前提でCodex対象外に近い |
| 15 | `strategic-compact.py` | C | 低 | 後回し | Codexのcompact周辺hookが不足。今は効果が薄い |

---

## 7. 実装するなら最初の具体案

最初に作るなら、`C:\Users\Tenormusica\.codex\hooks\` に Codex専用版として分けるのが良いです。Claude Code 版をそのまま上書き・共用しない方が安全です。

推奨ファイル構成:

```text
C:\Users\Tenormusica\.codex\hooks\
  codex_hook_utils.py
  codex_project_classifier.py
  stop_test_delegation_guard.py
  stop_completion_verification_guard.py
  pretool_git_guard.py
  user_prompt_doc_update_context.py
```

最初の `hooks.json` は小さくします。

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python C:/Users/Tenormusica/.codex/hooks/pretool_git_guard.py",
            "timeout": 5
          }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python C:/Users/Tenormusica/.codex/hooks/user_prompt_doc_update_context.py",
            "timeout": 5
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python C:/Users/Tenormusica/.codex/hooks/stop_test_delegation_guard.py",
            "timeout": 5
          },
          {
            "type": "command",
            "command": "python C:/Users/Tenormusica/.codex/hooks/stop_completion_verification_guard.py",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

注意: これは設計案です。現時点ではまだ配置・有効化はしていません。Codex では `/hooks` で trust / enable 状態を確認してから使う必要があります。

---

## 8. 判断まとめ

一番欲しいのは、**Codexが「終わりました」と言う前に、ユーザー丸投げ・テスト未実行・危険git操作を止めるセット**です。

そのため、初期導入はこの3つで十分です。

1. `test-delegation-detector.py` の Codex版
2. `completion-hook.py` の Codex版
3. `block-dangerous-git.sh` の Codex版

次に、文書運用を安定させるために `document-update-detector.py` を入れるのが良いです。`test-complete-hook.py` や `enforce-go-robust` は価値はありますが、Codex skill 体系へ置き換えが必要なので Phase 2 以降が安全です。