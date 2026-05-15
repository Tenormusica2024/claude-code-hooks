# external-task-completion-hook

`external-task-completion-hook.py` は、Claude Code / Codex の通常の `Stop` hook だけでは拾いにくい「外部ツール側のタスク完了」を受けて、完了前の証跡を確認するための汎用 completion gate です。

最初の利用想定は Pane Auto v2 の final preflight です。ただし、実装は Pane Auto 専用に閉じず、他の watcher / runner / scheduler からも同じ JSON 形式で呼べるようにしています。

## 狙い

Codex は Claude Code と比べて、会話中の「完了」「done」などの語彙に依存した検出が安定しにくいです。

そのため、モデルの自然文を毎回監視するより、以下のような **実行フロー上の節目** で gate を走らせます。

- watcher が `worked for` などの完了兆候を見た後
- Pane Auto v2 の final preflight が終了した時
- runner / scheduler / tool wrapper が「このタスクは終わり」と判断した時

## 今回の Pane Auto v2 preflight 用プロファイル

既定の `--profile pane-auto-v2-preflight` は、以下を確認します。

- preflight report の `ok` が `true`
- `steps` が存在する
- 各 step に `returncode` があり、値が 0
- dry-run ではない
- `pytest` / `test` 相当の step が含まれる

`manual_only_checks` や `recommended_live_test_handoff` がある場合は advisory として返します。
これは「preflight は通ったが、ユーザー実動作テストや live handoff はまだ別物」という境界を残すためです。

`PostToolUse` 経由で `pane_auto_v2_preflight.py` の実行を検知したのに JSON report が見つからない場合は block します。
これは、preflight 自体は起動したが stdout が壊れた / 切れた / wrapper が report を渡していない状態を成功扱いしないためです。

## 直接呼び出し

Pane Auto v2 preflight の JSON をそのまま渡す場合:

```powershell
python .\pane_auto_v2_preflight.py |
  python C:\Users\<USERNAME>\.claude\hooks\external-task-completion-hook.py --profile pane-auto-v2-preflight --require-report --strict-exit --json
```

dry-run を gate 成功扱いにしたい検証時だけ:

```powershell
python .\pane_auto_v2_preflight.py --dry-run |
  python C:\Users\<USERNAME>\.claude\hooks\external-task-completion-hook.py --profile pane-auto-v2-preflight --require-report --allow-dry-run --json
```

直接 wrapper として使う場合は `--require-report` を付けてください。
これにより、preflight が JSON を出す前に落ちた / stdout が空だったケースを no-op ではなく block として扱えます。

## PostToolUse hook として使う例

`Bash` / shell tool の完了後に hook し、コマンドが `pane_auto_v2_preflight.py` を含む場合だけ評価します。
関係ない Bash コマンドでは no-op です。
preflight stdout の前後に進捗ログや別の JSON が混じっても、`ok` と `steps` を持つ preflight report を探して評価します。

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python \"C:\\Users\\<USERNAME>\\.claude\\hooks\\external-task-completion-hook.py\" --profile pane-auto-v2-preflight"
          }
        ]
      }
    ]
  }
}
```

Codex 側で使う場合も考え方は同じです。Codex の `PostToolUse` / shell 系 matcher にこの hook を置き、preflight コマンドの stdout JSON を評価します。

## 追加オプション

final gate をより強くしたい場合だけ追加します。

| オプション | 用途 |
| --- | --- |
| `--require-clean-git` | `repo_root` の git worktree が clean でなければ block |
| `--require-pushed` | upstream より ahead の commit があれば block |
| `--require-doc-evidence` | report に doc 更新証跡がなければ block |
| `--require-report` | JSON report が無い場合に block。直接 wrapper 用 |
| `--no-require-test-step` | test step 必須を外す |
| `--allow-dry-run` | dry-run report を pass 扱いにする |
| `--strict-exit` | block 時に exit code 1 を返す |
| `--json` | pass / noop でも JSON を出す |

## 返却

block 時は hook 互換の JSON を stdout に出します。

```json
{
  "decision": "block",
  "reason": "[EXTERNAL TASK COMPLETION GATE BLOCKED] ...",
  "source": "pane_auto_v2_preflight",
  "blockers": ["..."],
  "advisories": ["..."],
  "evidence": {
    "ok": false,
    "step_count": 1,
    "failed_step_count": 1,
    "dry_run": false,
    "has_test_step": true,
    "repo_root": "..."
  }
}
```

通常の hook 用途では、pass / noop の時は何も出しません。
検証ログを見たい時だけ `--json` を付けます。
wrapper / CI / scheduled task から終了コードで判定したい場合は `--strict-exit` を付けると、block 時に exit code 1 を返します。

## 設計メモ

- 会話文の「完了」検出ではなく、tool / runner が出す構造化 JSON を見る。
- Pane Auto v2 preflight 以外の runner でも、`ok` と `steps` を持つ report に寄せれば流用できる。
- 毎回重いテストを起動する hook ではなく、「preflight / runner 終了時の証跡確認」に限定する。
- `--require-clean-git` / `--require-pushed` は強い gate なので、常時ONではなく final handoff 直前だけ使う。

