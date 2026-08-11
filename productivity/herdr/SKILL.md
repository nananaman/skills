---
name: herdr
description: Herdr が管理する pane 内で HERDR_ENV=1 を確認したうえで、herdr CLI による pane / tab / workspace / agent の確認、隣接 pane でのコマンド実行、出力待ち、agent 協調、管理対象の Hunk review のコメント回収を行う運用手順。Herdr 外、短い単発コマンド、承認のない focus / close / takeover / layout 変更 / 人間 pane への入力、管理対象の Hunk review pane の起動 / reload / close では使わない。
---

# Herdr

Herdr が管理する pane 内で、`herdr` CLI を安全に使うための skill。
CLI のコマンド一覧、用途別の運用手順、作業例は `references/herdr-cli-runbook.md` に分離している。
具体的なコマンド構文、選択肢、例が必要になった時点で読む。

## 契約

- 最初に `HERDR_ENV=1` を確認する。
- `HERDR_ENV` が `1` でなければ、Herdr-managed pane 外であることを報告して止める。
- Herdr 外から focused pane を推測して操作しない。
- workspace / tab / pane ID は stable handle として扱うが、pane move 後は新しい ID を response から取り直す。agent target は unique な live agent 名か、その agent を現在 host する pane ID に限定する。
- tab label は主タスクを表し、pane label は pane 固有の役割や作業を表す。
- 最初の実質的なタスクで、response に `name` がない現在 agent と番号だけの現在 tab を、タスク由来名へ一度だけ rename する。非番号の tab label は上書きせず agent 名の生成に使い、`name` がある agent は命名済みとして変更しない。
- 現在の generic agent の初回 rename と、番号だけの現在 tab の rename は自律実行してよい。pane label、別 agent、命名済み agent、非番号の tab label、`--clear` は自動変更の対象にしない。
- pane label を自動変更できるのは、agent が直前に作成した補助 pane だけとする。人間が管理する既存 pane とその label は変更しない。
- 補助用の pane / tab / workspace を作るときは、原則 `--no-focus` を付ける。
- focus / close / takeover / layout 変更 / 既存 pane への入力は、ユーザーが明示依頼した場合だけ実行する。
- 人間が見ている active pane に入力、focus 移動、close、takeover をしない。
- 短い単発 command は通常の shell tool を使い、この skill を使わない。
- managed Hunk review の起動、reload、close は agent が行わない。
- Hunk の user comment は、人間がレビュー完了を伝えた後だけ session API から回収する。

## 使用する場面

- 長時間 command、dev server、test、log tail を sibling pane に逃がしたい。
- 隣接 pane や helper agent の出力を読み、現在の作業を続けたい。
- command の readiness marker や test 完了を待ちたい。
- helper agent を別 pane で起動し、完了後に結果を読む必要がある。
- Herdr の workspace / tab / pane / agent 状態を確認しながら作業を進める。
- managed Hunk review の完了後に、人間が残したコメントを回収する。

## 使用しない場面

- `HERDR_ENV=1` ではない。
- `exec_command` など通常の shell tool で短く完結する。
- ユーザーが見ている pane を無断で操作する必要がある。
- focus / close / takeover / layout 変更を、ユーザー承認なしに行う必要がある。
- Herdr CLI 自体の実装、設定ファイル、配布、更新を調査する作業。必要なら通常の repo 調査として扱う。

## 手順

1. 事前確認を行う。

   ```sh
   printf '%s\n' "${HERDR_ENV-}"
   herdr status --json
   herdr pane current
   herdr pane list
   ```

   `HERDR_ENV` が `1` でない、または `herdr status` が失敗する場合は止める。

2. 作業種別を決める。
   - 初回命名: 現在 agent の response に `name` がなければ、runbook の初回命名手順を一度だけ実行する。
   - 読むだけ: `pane read` / `agent read` / list / get 系に限定する。
   - 補助 pane で実行: `pane split --no-focus` で shell pane を作り、必要ならその pane を指定して `agent start` を使う。
   - 待機: 通常 command は `pane wait-output`、agent は `agent wait` を使い、最後に read で結果を確認する。
   - risky operation: 実行せず、対象 ID・操作・影響を提示してユーザー承認を待つ。

3. 具体 command が必要なら `references/herdr-cli-runbook.md` を読む。
   - CLI 全体構造。
   - pane 読み取り / split / run / send。
   - wait / agent / workspace / tab 操作。
   - task pattern と troubleshooting。

4. 実行後に結果を報告する。
   - 実行した Herdr command の要約。
   - 読んだ workspace / tab / pane / agent ID。
   - 起動した command、待機条件、結果。
   - timeout / failure があれば原因候補と次の選択肢。
   - focus / close / takeover / 既存 pane 入力が必要なら、実行せず承認待ちにする。

## 安全な基本手順

### 隣接 pane を読む

```sh
herdr pane current
herdr pane list
herdr pane read <pane-id> --source recent --lines 80
```

### 長時間コマンドを隣接 pane で実行する

```sh
CURRENT_PANE=$(herdr pane current \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["result"]["pane"]["pane_id"])')
NEW_PANE=$(herdr pane split "$CURRENT_PANE" --direction right --no-focus \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["result"]["pane"]["pane_id"])')
herdr pane run "$NEW_PANE" "<command>"
herdr pane wait-output "$NEW_PANE" --match "<marker>" --timeout 60000
herdr pane read "$NEW_PANE" --source recent --lines 100
```

### 補助 agent を起動して読む

```sh
herdr agent list
HELPER_PANE=$(herdr pane split --current --direction right --cwd "$PWD" --no-focus \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["result"]["pane"]["pane_id"])')
herdr pane rename "$HELPER_PANE" "Review test structure"
herdr agent start review-test-structure --kind claude --pane "$HELPER_PANE"
herdr agent prompt "$HELPER_PANE" "<task>" --wait --timeout 120000
herdr agent read "$HELPER_PANE" --source recent --lines 120
```

## 管理対象の Hunk review

Hunk review pane は Herdr plugin と人間が管理する。
agent は Hunk pane を起動、reload、close しない。
pane の表示内容は全コメントを含む保証がないため、コメント回収の source of truth にしない。

人間が「レビュー完了」または同等の完了を伝えた後、現在の repository について Hunk session を確認する。

```sh
hunk session get --repo .
hunk session comment list --repo . --type user
```

- Hunk session が見つからない場合は、コメント0件として扱わず、session 未検出を報告する。
- コメントがある場合は、原文、file、line、hunk 情報を保持して整理する。
- コメントが0件の場合も自動承認せず、「指摘なしとして進めてよいですか？」と確認する。
- コメント取得後、修正または commit へ進む前に人間へ対応方針を確認する。
- レビュー完了後も Hunk pane をcloseせず、watchを継続させる。

## 危険な操作の承認条件

次の操作は通常の手順から外す。
ユーザーが明示依頼した場合だけ、実行前に対象 ID、現在の process / agent 状態、操作内容、予想される影響を提示する。
ただし、直前にこの作業のために作成した補助 pane / helper agent への `pane run` / `agent prompt` は通常 path として扱う。

| 操作 | 例 |
|---|---|
| focus 移動 | `pane focus`、`tab focus`、`workspace focus`、`agent focus` |
| close | `pane close`、`tab close`、`workspace close` |
| 既存 pane / 既存 agent 入力 | `pane run`、`send-text`、`send-keys`、`agent prompt`、`agent send-keys` |
| takeover / attach | `agent attach`、`agent attach --takeover` |
| layout 変更 | `pane move`、`swap`、`resize`、`zoom` |
| metadata 注入 | `pane report-*` |

## 失敗時の処理

- `HERDR_ENV` がない: Herdr 操作を止め、通常 shell tool で代替できるか提案する。
- `herdr` command が失敗する: command、exit code、stderr を報告し、追加操作へ進まない。
- ID が見つからない / 古い: list / current / get を読み直し、推測で補正しない。
- wait が timeout、または `agent_prompt_stalled`: `pane read` / `agent get` / `agent read` で直近状態を確認し、失敗・実行中・marker 不一致・state change 未検出を切り分ける。
- TUI 出力が読みにくい: `--format ansi` または `--source recent-unwrapped` を使う。
