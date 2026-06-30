---
name: herdr
description: Herdr-managed pane 内で作業しているとき、herdr CLI で workspace / tab / pane を確認・分割し、隣接 pane で command や agent を起動し、出力や agent status を待つ。HERDR_ENV=1 でない場合や、Herdr 外から focused pane を操作する用途では使わない。
---

# Herdr

Herdr-managed pane の中で、`herdr` CLI を使って workspace / tab / pane を操作する。

## Guardrail

この skill を使う前に、必ず `HERDR_ENV=1` か確認する。
`HERDR_ENV` が `1` でなければ、Herdr-managed pane の中で実行されていないことを伝えて止める。
Herdr 外から focused pane を推測して操作しない。

```sh
printf '%s\n' "${HERDR_ENV-}"
```

## 使う場面

- 隣接 pane の出力や agent status を確認する。
- 長時間 command、dev server、test、log tail を sibling pane で実行する。
- workspace / tab / pane を作成・focus・rename・close する。
- 別 pane で helper agent を起動する。
- command や agent の出力を待ってから次に進む。

短い単発 command、通常の shell tool だけで足りる作業、人間が操作中の pane へ無断入力する作業では使わない。

## 基本概念

- workspace: project context。複数 tab を持つ。
- tab: workspace 内の subcontext。複数 pane を持つ。
- pane: terminal split。shell、agent、server、log stream などが動く。
- agent status: `idle`、`working`、`blocked`、`done`、`unknown`。

ID は live session 内の compact public ID で、workspace / tab / pane を閉じると詰め直されることがある。
古い ID を durable ID として扱わず、操作前に `workspace list`、`tab list`、`pane list`、または create / split の返り値から取り直す。

## 自分と周辺 pane を確認する

```sh
herdr workspace list
herdr tab list --workspace <workspace-id>
herdr pane list
```

`pane list` で focused な pane が現在の pane。他の pane は neighbor として扱う。

## pane の出力を読む

```sh
herdr pane read <pane-id> --source recent --lines 50
```

`--source` の使い分け:

- `visible`: 現在の viewport。
- `recent`: 最近の scrollback を terminal 表示どおりに読む。
- `recent-unwrapped`: soft wrap を戻した最近の text。`wait output` の match 対象確認に使う。

ANSI を含む TUI 表示が必要なら `--format ansi` または `--ansi` を使う。

## pane を分割して command を実行する

現在 pane の ID を `pane list` で確認してから、`--no-focus` で sibling pane を作る。

```sh
NEW_PANE=$(herdr pane split <pane-id> --direction right --no-focus \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["result"]["pane"]["pane_id"])')
herdr pane run "$NEW_PANE" "npm run dev"
```

下方向に分割する場合:

```sh
NEW_PANE=$(herdr pane split <pane-id> --direction down --no-focus \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["result"]["pane"]["pane_id"])')
```

`pane run` は text を送って Enter を押す。
Enter なしで送るなら `pane send-text`、key 操作なら `pane send-keys` を使う。

```sh
herdr pane send-text <pane-id> "hello"
herdr pane send-keys <pane-id> Enter
```

## 出力を待つ

server、build、test などの readiness や完了 marker を待つ。

```sh
herdr wait output <pane-id> --match "ready" --timeout 30000
```

regex match:

```sh
herdr wait output <pane-id> --match "server.*ready" --regex --timeout 30000
```

timeout すると exit code は `1`。
待機後に結果を確認する。

```sh
herdr pane read <pane-id> --source recent --lines 40
```

## agent status を待つ

別 pane の agent が終わるまで待つ。

```sh
herdr wait agent-status <pane-id> --status done --timeout 120000
herdr pane read <pane-id> --source recent --lines 100
```

`done` は agent が終了したが、その pane をまだ見ていない状態を表す。

## tab / workspace 操作

```sh
herdr tab create --workspace <workspace-id> --label "logs" --no-focus
herdr tab focus <tab-id>
herdr tab rename <tab-id> "logs"
herdr tab close <tab-id>
```

```sh
herdr workspace create --cwd /path/to/project --label "api" --no-focus
herdr workspace focus <workspace-id>
herdr workspace rename <workspace-id> "api"
herdr workspace close <workspace-id>
```

## recipes

### server を sibling pane で起動して待つ

```sh
herdr pane list
NEW_PANE=$(herdr pane split <current-pane-id> --direction right --no-focus \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["result"]["pane"]["pane_id"])')
herdr pane run "$NEW_PANE" "npm run dev"
herdr wait output "$NEW_PANE" --match "ready" --timeout 30000
herdr pane read "$NEW_PANE" --source recent --lines 40
```

### test を sibling pane で実行して結果を見る

```sh
herdr pane list
NEW_PANE=$(herdr pane split <current-pane-id> --direction down --no-focus \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["result"]["pane"]["pane_id"])')
herdr pane run "$NEW_PANE" "cargo test"
herdr wait output "$NEW_PANE" --match "test result" --timeout 60000
herdr pane read "$NEW_PANE" --source recent --lines 80
```

### helper agent を sibling pane で起動する

```sh
herdr pane list
NEW_PANE=$(herdr pane split <current-pane-id> --direction right --no-focus \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["result"]["pane"]["pane_id"])')
herdr pane run "$NEW_PANE" "claude"
herdr wait output "$NEW_PANE" --match ">" --timeout 15000
herdr pane run "$NEW_PANE" "review the test coverage in src/api/"
```

使う agent CLI と初期 prompt は環境に合わせる。

## command の出力形式

- `workspace list/create`、`tab list/create/get`、`pane list/get/split`、`wait output`、`wait agent-status` は成功時に JSON を出す。
- `pane read` は text を出す。
- `pane send-text`、`pane send-keys`、`pane run` は成功時に何も出さない。
- create / split 後の ID は JSON response から parse する。

## Upstream

この skill は Herdr upstream の agent skill を個人運用向けに整理したもの。
仕様確認が必要な場合は upstream を見る。

- Source: https://github.com/ogulcancelik/herdr/blob/master/SKILL.md
- Docs: https://herdr.dev/docs/agent-skill/
- Socket API: https://herdr.dev/docs/socket-api/
