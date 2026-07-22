# Herdr CLI Runbook Reference

この reference は `herdr --help` / `herdr <group> --help` で確認できる CLI の事実と、この repository の Herdr 運用ルールを用途別に整理したもの。


# Herdr CLI Runbook

Herdr-managed pane 内で、`herdr` CLI を安全に使うための runbook。
Herdr の実装や開発ではなく、実行中の Herdr session に対する観測、pane 分割、command 実行、出力待ち、agent 協調を扱う。

この skill の command map は `herdr --help` / `herdr <group> --help` で確認できる CLI の事実を前提にする。
詳細が不明な subcommand は、実行前に該当 help を読む。

## Contract

- 最初に `HERDR_ENV=1` を確認する。
- `HERDR_ENV` が `1` でなければ、Herdr-managed pane 外であることを報告して止める。
- Herdr 外から focused pane を推測して操作しない。
- workspace / tab / pane ID は stable handle として扱うが、pane move 後は新しい ID を response から取り直す。agent target は unique な live agent 名か、その agent を現在 host する pane ID に限定する。
- 補助用の pane / tab / workspace を作るときは、原則 `--no-focus` を付ける。
- focus / close / takeover / layout 変更 / 既存 pane への入力は、ユーザーが明示依頼した場合だけ実行する。
- 人間が見ている active pane に入力、focus 移動、close、takeover をしない。
- 短い単発 command は通常の shell tool を使い、この skill を使わない。

## When to use

- 長時間 command、dev server、test、log tail を sibling pane に逃がしたい。
- 隣接 pane や helper agent の出力を読み、現在の作業を続けたい。
- command の readiness marker や test 完了を待ちたい。
- helper agent を別 pane で起動し、完了後に結果を読む必要がある。
- Herdr の workspace / tab / pane / agent 状態を確認しながら作業を進める。

## When not to use

- `HERDR_ENV=1` ではない。
- `exec_command` など通常の shell tool で短く完結する。
- ユーザーが見ている pane を無断で操作する必要がある。
- focus / close / takeover / layout 変更を、ユーザー承認なしに行う必要がある。
- Herdr CLI 自体の実装、設定ファイル、配布、更新を調査する作業。必要なら通常の repo 調査として扱う。

## Preflight

### Herdr 内か確認する

```sh
printf '%s\n' "${HERDR_ENV-}"
```

- 出力が `1` でなければ止める。
- Herdr 内であることだけでは対象 ID は確定しない。次に status / current / list で現在地を確認する。

### client / server 状態を確認する

```sh
herdr status
herdr status --json
herdr status server --json
herdr status client --json
```

- socket / server に接続できない場合は、実行した command と error を報告して止める。
- JSON が必要なときだけ `--json` を使う。

### 現在地を確認する

```sh
herdr workspace list
herdr tab list --workspace <workspace-id>
herdr pane current
herdr pane list
```

- `pane current` で自分の pane を確認する。
- `pane list` で周辺 pane を把握する。
- workspace / tab を跨ぐ操作では、先に `workspace list` と `tab list` を読む。

## CLI の全体構造

| Group | よく使う用途 |
|---|---|
| `status` | client / server 状態確認 |
| `workspace` | workspace の list / create / get / focus / rename / close |
| `tab` | tab の list / create / get / focus / rename / close |
| `pane` | pane の list / current / get / read / split / run / send / layout 操作 |
| `agent` | agent の list / get / read / start / prompt / send-keys / wait / attach |

help:

```sh
herdr --help
herdr status --help
herdr workspace --help
herdr tab --help
herdr pane --help
herdr agent --help
```

## Read-only observation

まず read-only command で状況を確認する。
read-only のつもりでも、対象 ID が古いと別 pane を読む可能性があるため、直前に ID を取り直す。

### workspace / tab / pane を列挙する

```sh
herdr workspace list
herdr workspace get <workspace-id>
herdr tab list --workspace <workspace-id>
herdr tab get <tab-id>
herdr pane list --workspace <workspace-id>
herdr pane current
herdr pane get <pane-id>
```

`pane list --workspace` は workspace を絞りたいときに使う。
現在 pane だけでよいなら `pane current` を使う。

### pane の位置や process を調べる

```sh
herdr pane layout --current
herdr pane process-info --current
herdr pane neighbor --direction right --current
herdr pane edges --current
```

- `layout` は split 構造確認。
- `process-info` は対象 pane で動いている process の確認。
- `neighbor` / `edges` は隣接 pane や端判定に使う。
- これらは調査用。操作に進む前に対象 ID を再確認する。

### pane の出力を読む

```sh
herdr pane read <pane-id> --source recent --lines 50
herdr pane read <pane-id> --source visible --lines 50
herdr pane read <pane-id> --source recent-unwrapped --lines 80
herdr pane read <pane-id> --source visible --format ansi
```

| source / format | 使いどころ |
|---|---|
| `visible` | 現在 viewport の見た目を確認する |
| `recent` | 最近の scrollback を読む通常 path |
| `recent-unwrapped` | soft wrap が邪魔な matcher / log 確認 |
| `--format ansi` / `--ansi` | TUI や色付き表示を残して見る |

出力が多い場合は `--lines` を小さくして、必要な marker だけ読む。

## Running work in another pane

長時間 command は sibling pane を作って実行する。
現在 pane を奪わないため、split / create には原則 `--no-focus` を付ける。

### 基本パターン

```sh
CURRENT_PANE=$(herdr pane current \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["result"]["pane"]["pane_id"])')
NEW_PANE=$(herdr pane split "$CURRENT_PANE" --direction right --no-focus \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["result"]["pane"]["pane_id"])')
herdr pane run "$NEW_PANE" "npm run dev"
```

- `pane split` は `--direction right|down` を使う。
- 必要なら `--ratio FLOAT`、`--cwd PATH`、`--env KEY=VALUE` を付ける。
- command 実行後は `wait` または `pane read` で結果を確認する。

### 入力系 command の使い分け

```sh
herdr pane run <pane-id> "cargo test"
herdr pane send-text <pane-id> "hello"
herdr pane send-keys <pane-id> Enter
```

| command | 使いどころ | 注意 |
|---|---|---|
| `pane run` | command text を送り Enter まで押す | 補助 pane 向け |
| `pane send-text` | text だけ送る | 既存 pane では承認 gate |
| `pane send-keys` | Enter など key を送る | 既存 pane では承認 gate |

既存 pane に入力する場合は、対象 pane、送る text / key、影響をユーザーへ提示し、明示承認を得る。

### pane 名を付ける

```sh
herdr pane rename <pane-id> "dev server"
herdr pane rename <pane-id> --clear
```

補助 pane の用途が分かりにくい場合だけ rename する。
rename は destructive ではないが、既存の人間管理ラベルを上書きしうるため、既存 pane では慎重に扱う。

## Waiting

待機 command は、長時間 command を投げた後に使う。
待機だけで完了扱いにせず、最後に `pane read` / `agent read` で結果を確認する。

### 出力を待つ

```sh
herdr pane wait-output <pane-id> --match "ready" --timeout 30000
herdr pane wait-output <pane-id> --match "test result" --source recent --lines 120 --timeout 60000
herdr pane wait-output <pane-id> --regex "server.*ready" --timeout 30000
herdr pane wait-output <pane-id> --match "raw text" --raw --timeout 30000
```

- `--timeout` は ms。
- `--regex` は pattern として match したい場合だけ使う。
- `--raw` は match text を raw に扱いたい場合だけ使う。
- timeout したら、exit code と直近出力を確認して報告する。

### agent status を待つ

```sh
herdr agent wait <target> --until done --timeout 120000
herdr agent wait <target> --until idle --timeout 60000
```

status 候補は `idle`、`working`、`blocked`、`done`、`unknown`。
待機後は対象 pane を読む。

```sh
herdr pane read <pane-id> --source recent --lines 100
```

## Agent operations

agent subcommands は、unique な live agent name またはその agent を現在 host する pane ID を target として扱う。
曖昧な target は使わず、`agent list` と `agent get` で確認する。

### agent を観測する

```sh
herdr agent list
herdr agent get <target>
herdr agent read <target> --source recent --lines 100
herdr agent read <target> --source visible --format ansi
```

agent の進捗確認は、まず read-only で行う。

### agent に prompt を送る

```sh
herdr agent prompt <target> "次の観点で調査してください: ..." --wait --timeout 120000
```

- `agent prompt` は text と Enter を atomic に送り、live bracketed-paste mode を尊重する。
- `--wait` は既定で、送信後に最初に観測した settled state（`idle`、`done`、`blocked`）を待つ。
- 特定状態だけを待つ必要がある場合に限り、`--until <status>` を追加する。
- shell command と Enter を送りたい場合は `pane run` を使う。
- 既存 agent に依頼を追加する前に、その agent が誰の作業か、割り込みにならないかを確認する。

### agent を起動する

```sh
herdr agent list
AGENT_PANE=$(herdr pane split --current --direction right --cwd /path/to/repo --no-focus \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["result"]["pane"]["pane_id"])')
herdr agent start helper --kind claude --pane "$AGENT_PANE"
```

- `agent start` 自体は layout を変更しない。interactive shell が foreground で待機している既存 pane を `--pane` で指定する。
- `--kind` には起動する agent kind を指定する。native agent 引数は `--` より後ろへ渡す。
- `agent list` を起動前に読み、agent 名が `[a-z][a-z0-9_-]{0,31}` を満たし、live agent 間で unique になるよう選ぶ。

### agent 完了を待つ

```sh
herdr agent wait <target> --timeout 120000
herdr agent wait <target> --until blocked --timeout 120000
herdr agent read <target> --source recent --lines 120
```

`--until` を省略した `agent wait` は `idle`、`done`、`blocked` のいずれかを待つ。
status 候補は `idle`、`working`、`blocked`、`done`、`unknown`。

agent UI に key を送る必要がある場合は、全keyを事前検証する `agent send-keys` を使う。

```sh
herdr agent send-keys <target> esc
herdr agent send-keys <target> ctrl+c
```

### attach / takeover

```sh
herdr agent attach <target>
herdr agent attach <target> --takeover
```

attach / takeover は agent や人間の操作状態に影響する。
ユーザーが明示的に依頼した場合だけ、対象 target と影響を提示して実行する。

metadata / report 系（`pane report-agent`、`pane report-agent-session`、`pane release-agent`、`pane report-metadata`）は通常の作業では使わない。agent integration や metadata reporting を明示的に扱う場合だけ、該当 command の help を確認してから実行する。

## Workspace / tab operations

workspace / tab は subcontext を分けるために使う。
作成は `--no-focus` を基本にし、focus / close は承認 gate を通す。

### workspace

```sh
herdr workspace list
herdr workspace create --cwd /path/to/project --label "api" --no-focus
herdr workspace get <workspace-id>
herdr workspace rename <workspace-id> "api"
herdr workspace focus <workspace-id>
herdr workspace close <workspace-id>
```

- `create` では `--env KEY=VALUE` を渡せる。
- `focus` / `close` はユーザー明示依頼時のみ。
- `close` 前には対象 workspace、含まれる tab / pane、実行中 process の有無を確認する。

### tab

```sh
herdr tab list --workspace <workspace-id>
herdr tab create --workspace <workspace-id> --cwd /path/to/project --label "logs" --no-focus
herdr tab get <tab-id>
herdr tab rename <tab-id> "logs"
herdr tab focus <tab-id>
herdr tab close <tab-id>
```

- `create` では `--env KEY=VALUE` を渡せる。
- `focus` / `close` はユーザー明示依頼時のみ。
- 補助用途では既存 tab を奪わず、新規 tab / pane を `--no-focus` で作る。

## Layout and risky pane operations

次の操作は人間の作業画面や実行中 process に影響しやすい。
通常 workflow から外し、必要性、対象 ID、予想される影響をユーザーへ提示して承認を得る。

| Operation | Command | Gate |
|---|---|---|
| focus 移動 | `pane focus --direction ...` / `tab focus` / `workspace focus` / `agent focus` | 明示依頼時のみ |
| close | `pane close` / `tab close` / `workspace close` | 対象確認 + 明示依頼 |
| 既存 pane 入力 | `pane run` / `send-text` / `send-keys` / `agent prompt` / `agent send-keys` | 補助 pane 以外は明示依頼 |
| takeover / attach | `agent attach [--takeover]` | 明示依頼時のみ |
| layout 変更 | `pane move` / `swap` / `resize` / `zoom` | 必要性説明 + 明示依頼 |
| metadata 注入 | `pane report-*` | integration 作業時のみ |

利用可能な layout command:

```sh
herdr pane resize --direction left --amount 0.1 --current
herdr pane zoom --current --toggle
herdr pane swap --direction right --current
herdr pane swap --source-pane <pane-id> --target-pane <pane-id>
herdr pane move <pane-id> --tab <tab-id> --split right --no-focus
herdr pane move <pane-id> --new-tab --workspace <workspace-id> --label "logs" --no-focus
herdr pane move <pane-id> --new-workspace --label "api" --tab-label "logs" --no-focus
```

## Task patterns

### 隣の pane を読むだけ

```sh
herdr pane current
herdr pane list
herdr pane read <target-pane-id> --source recent --lines 80
```

報告には、読んだ pane ID、直近出力の要点、追加操作が必要かを書く。

### dev server を sibling pane で起動する

```sh
CURRENT_PANE=$(herdr pane current \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["result"]["pane"]["pane_id"])')
SERVER_PANE=$(herdr pane split "$CURRENT_PANE" --direction right --no-focus \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["result"]["pane"]["pane_id"])')
herdr pane rename "$SERVER_PANE" "dev server"
herdr pane run "$SERVER_PANE" "npm run dev"
herdr pane wait-output "$SERVER_PANE" --match "ready" --timeout 30000
herdr pane read "$SERVER_PANE" --source recent --lines 60
```

ready marker は project に合わせて変える。
timeout したら直近出力を読んで、server が起動中か失敗したかを報告する。

### test / build を sibling pane で実行する

```sh
CURRENT_PANE=$(herdr pane current \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["result"]["pane"]["pane_id"])')
TEST_PANE=$(herdr pane split "$CURRENT_PANE" --direction down --no-focus \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["result"]["pane"]["pane_id"])')
herdr pane rename "$TEST_PANE" "test"
herdr pane run "$TEST_PANE" "cargo test"
herdr pane wait-output "$TEST_PANE" --match "test result" --timeout 60000
herdr pane read "$TEST_PANE" --source recent --lines 100
```

終了 marker が分からない場合は、timeout を短めにして read し、追加で待つか判断する。

### log tail を隔離する

```sh
LOG_PANE=$(herdr pane split --current --direction right --no-focus \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["result"]["pane"]["pane_id"])')
herdr pane rename "$LOG_PANE" "logs"
herdr pane run "$LOG_PANE" "tail -f ./logs/app.log"
herdr pane wait-output "$LOG_PANE" --match "ERROR" --timeout 120000
herdr pane read "$LOG_PANE" --source recent --lines 80
```

tail は終わらない前提。
不要になった pane を close する場合はユーザー承認を得る。

### helper agent を別 pane で起動する

```sh
herdr agent list
HELPER_PANE=$(herdr pane split --current --direction right --cwd "$PWD" --no-focus \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["result"]["pane"]["pane_id"])')
herdr agent start helper --kind claude --pane "$HELPER_PANE"
herdr agent wait helper --timeout 120000
herdr agent read helper --source recent --lines 120
```

agent 起動後に task を送る場合:

```sh
herdr agent prompt helper "この repository の test 構成を調査して、200字以内で報告してください。" --wait --timeout 120000
herdr agent read helper --source recent --lines 120
```

target 名が曖昧なら `agent list` / `agent get` で確認してから送る。

## Failure handling

### `HERDR_ENV` がない

- Herdr-managed pane 外なので、この skill の操作は止める。
- 代替として通常の shell tool で実行できるか提案する。

### `herdr` command が失敗する

- 実行した command、exit code、stderr を報告する。
- `herdr status --json` が読めるか確認する。
- socket / server 不通なら、それ以上の操作へ進まない。

### ID が見つからない / 古い

- `workspace list`、`tab list`、`pane list`、`agent list` を読み直す。
- 古い ID を推測で補正しない。
- 候補が複数ある場合はユーザーに確認する。

### wait が timeout する、または prompt が stalled になる

```sh
herdr pane read <pane-id> --source recent --lines 100
```

- timeout した match と timeout ms を報告する。
- `agent_prompt_stalled` の場合は、`agent get` と `agent read` でstate changeが観測されなかった理由を確認する。
- 直近出力から、失敗、まだ実行中、marker が不適切、出力 source が違う、のどれかを切り分ける。
- 追加で待つ場合も、条件を変える場合も理由を書く。

### TUI 出力が読みにくい

```sh
herdr pane read <pane-id> --source visible --format ansi
herdr pane read <pane-id> --source recent-unwrapped --lines 80
```

- 見た目が必要なら ANSI。
- text match / log 解析が目的なら unwrapped。

## Output

Herdr 操作を行ったら、最後に次を短く報告する。

- 実行した Herdr command の要約。
- 読んだ workspace / tab / pane / agent ID。
- 起動した command、待機条件、結果。
- timeout / failure があれば原因候補と次の選択肢。
- focus / close / takeover / 既存 pane 入力が必要なら、実行せずに承認待ちとして提示する。

## Quick Reference

| やりたいこと | command |
|---|---|
| Herdr 内判定 | `printf '%s\n' "${HERDR_ENV-}"` |
| 状態確認 | `herdr status --json` |
| workspace 一覧 | `herdr workspace list` |
| tab 一覧 | `herdr tab list --workspace <workspace-id>` |
| pane 一覧 | `herdr pane list` |
| 現在 pane | `herdr pane current` |
| pane 出力 | `herdr pane read <pane-id> --source recent --lines 50` |
| TUI 表示 | `herdr pane read <pane-id> --source visible --format ansi` |
| 右分割 | `herdr pane split <pane-id> --direction right --no-focus` |
| 下分割 | `herdr pane split <pane-id> --direction down --no-focus` |
| command 実行 | `herdr pane run <pane-id> "<command>"` |
| text 送信 | `herdr pane send-text <pane-id> "<text>"` |
| key 送信 | `herdr pane send-keys <pane-id> Enter` |
| 出力待ち | `herdr pane wait-output <pane-id> --match "ready" --timeout 30000` |
| regex 待ち | `herdr pane wait-output <pane-id> --regex "server.*ready" --timeout 30000` |
| agent 一覧 | `herdr agent list` |
| agent 読み取り | `herdr agent read <target> --source recent --lines 100` |
| agent 起動 | `herdr agent start <name> --kind <kind> --pane <pane-id> -- <agent-args...>` |
| agent prompt | `herdr agent prompt <target> "<text>" --wait --timeout 120000` |
| agent key | `herdr agent send-keys <target> esc` |
| agent 待機 | `herdr agent wait <target> --timeout 120000` |
| tab 作成 | `herdr tab create --workspace <workspace-id> --label "logs" --no-focus` |
| workspace 作成 | `herdr workspace create --cwd /path/to/project --label "api" --no-focus` |
