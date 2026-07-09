---
name: hunk-human-review
description: commit 前に Hunk TUI で未ステージ差分を人間レビュー依頼し、進行中の Hunk 人間レビューで「レビュー完了」と言われたらコメントを回収する。Hunk で人間に確認してもらう、commit 前に未ステージ差分を人間へ見せる、「レビューさせて」のようにユーザー本人がレビューしたい依頼で使う。詳細コードレビュー、修正、commit、PR 作成、単なる「レビューして」では使わない。
---

# Hunk Human Review

未ステージ差分を Hunk TUI で人間に見せ、レビュー完了後にコメントを回収する。
詳細レビューや修正判断はしない。Hunk を用意し、レビュー対象と手順を明示して止まる。

## When to use

- ユーザーが Hunk で差分を見たい、commit 前に見せてほしい、と依頼したとき。
- 「レビューさせて」のように、ユーザー本人がレビューしたい意図が自然なとき。
- レビュー完了後に Hunk コメントを回収して整理するとき。

使わない場面:

- agent に詳細コードレビューしてほしい依頼。
- 修正、commit、PR 作成だけの依頼。
- staged diff だけをレビューしたい依頼（この skill は未ステージ差分だけを扱う）。

## Contract

- 対象は **未ステージ差分** だけ。
- untracked の作業対象ファイルは `git add -N` で intent-to-add にし、内容は stage しない。
- 既存 Hunk session / Hunk tab を無断で reload、再利用、close しない。
- Herdr 環境では `herdr` skill の guardrail に従い、focus を奪わない。
- レビュー依頼を出したら、人間レビュー完了まで停止する。
- コメント 0 件を自動承認扱いしない。

## Workflow

通常 path では、この `SKILL.md` と同じ directory にある `scripts/hunk-human-review` を絶対 path で使う。
以降の例では、その絶対 path を `$HUNK_HUMAN_REVIEW` と書く。
fallback command は script が壊れた、または手元の環境で実行できない場合だけ使う。

1. `$HUNK_HUMAN_REVIEW preflight` を実行し、JSON の `ok`、`reviewable`、`review_ready`、`needs_intent_to_add`、`staged_out_of_scope`、`stop_reasons` を確認する。
2. untracked があれば作業対象 path を確認し、必要な path だけ `git add -N` で intent-to-add にする。
3. 既存 Hunk session / Hunk tab を確認し、再利用・reload・新規作成の方針が未確認なら止まる。
4. Hunk を開く。
5. `$HUNK_HUMAN_REVIEW request-markdown` を seed にレビュー依頼を作り、軽い変更サマリとレビュー方法を提示して人間レビュー完了まで停止する。
6. ユーザーが「レビュー完了」または同等の完了を伝えたら、`$HUNK_HUMAN_REVIEW comments` でコメントを回収する。
7. コメントを原文つきで整理し、修正・commit へ進む前にユーザー確認を取る。
8. 追加レビューや同じ Hunk tab の継続利用が必要なら、`$HUNK_HUMAN_REVIEW snapshot` で stale 判定する。stale または判定不能なら reload / 新規 tab / 中止を確認して止まる。
9. コメント回収と次アクション確認が終わってから、今回使った Hunk 専用 tab を閉じる。

## Preflight

通常 path:

```sh
"$HUNK_HUMAN_REVIEW" preflight
```

JSON の扱い:

- `hunk.available: false`、Git repo 外、`reviewable: false` の場合は止める。
- `review_ready: true` なら Hunk が見られる未ステージ差分がある。
- `staged_out_of_scope: true` の場合は、staged 変更が Hunk 対象外であることをレビュー依頼文に明示する。
- `needs_intent_to_add: true` の場合は `status.untracked_paths` で untracked path を確認し、作業対象だけを NUL-safe pathspec で `git add -N` する。
  - 全 untracked path が作業対象なら `git ls-files --others --exclude-standard -z > <tmp>` → `git add -N --pathspec-from-file=<tmp> --pathspec-file-nul` を使う。
  - unrelated path を除く場合は、確認済み path だけを NUL 区切りで `<tmp>` に書き、同じ `git add -N --pathspec-from-file=<tmp> --pathspec-file-nul` を使う。`git status --short` の行を shell 分割しない。
  - 実行後に `$HUNK_HUMAN_REVIEW preflight` を再実行し、`review_ready: true` と対象 path を確認する。
  - `git add -N` が非通常ファイル、権限、unrelated dotfiles などで失敗した場合は、作業対象として把握している新規ファイルだけに絞って再実行する。作業対象を特定できない場合は、対象 path をユーザーに確認して止まる。
  - intent-to-add した path set を保持する。途中で止まる場合は、intent-to-add が残ることを報告し、戻す操作はユーザー確認後だけ行う。

fallback command:

```sh
command -v hunk
git rev-parse --show-toplevel
git status --short --untracked-files=all
```

## Opening Hunk

### 共通

- `hunk session get --repo .` で既存 session を確認する。
- 既存 session がある場合は、それを使ってよいか確認して止まる。許可なしに reload、comment 削除、note 変更をしない。
- Hunk 起動後は `hunk session list` / `hunk session get --repo .` / `hunk session review --repo . --json` で確認する。
- session が短時間見つからなくても、Hunk pane / terminal に TUI が開いていればレビュー依頼へ進んでよい。ただしコメント回収できない可能性を明示する。

### Herdr 環境

`HERDR_ENV=1` なら `herdr` skill を使う。

- 現在 workspace と既存 `hunk-review` tab を確認する。
- 既存 tab がある場合は、「既存 tab を使う / 新規 tab を作る / 中止」をユーザーに確認する。
- 既存 tab を使う許可があっても、`herdr pane read` で表示中 diff が今回の repo / 対象差分か確認する。
  - 別 diff、stale diff、対象外ファイルが主に表示されている場合は、勝手に reload しない。「既存を reload / 新規 tab を作る / 中止」を確認する。
- 新規 tab は同じ workspace に `--no-focus` で作成する。
- 今回使った `tab_id` と `pane_id` を記録する。レビュー完了後に閉じる対象に使う。

### Herdr 外

自動 pane 操作はしない。ユーザーに別 terminal で次を実行してもらう。

```sh
hunk diff
```

## Review request format

通常 path:

```sh
"$HUNK_HUMAN_REVIEW" request-markdown
```

script 出力を seed にし、LLM は次だけを補う。

- 変更概要を `git status --short` と `git diff --stat` から 3〜5 行に要約する。
- 見てほしい観点を今回の変更に合わせて 2〜3 点へ絞る。
- staged 変更がある場合は Hunk 対象外であることを残す。
- untracked が元はあった場合は `git add -N` 済みで Hunk 対象になっているか確認してから書く。

出力形式の source of truth は script 側に置く。
次の section が残っていることだけ確認する。

- `## Hunk レビュー依頼`
- `### 変更概要`
- `### 注意`
- `### 見てほしい観点`
- `### レビュー方法`

詳細レビュー、問題指摘、agent comment の事前投入はしない。

## After review

ユーザーがレビュー完了を伝えたら、通常 path でコメントを回収する。

```sh
"$HUNK_HUMAN_REVIEW" comments
```

script は `hunk session comment list --repo . --type all` を必ず実行し、出力が空または疑わしい場合は `--type user` に fallback する。
JSON の `commands`、`fallback_user_used`、`state`、`comments`、`raw` を確認する。

fallback command:

```sh
hunk session comment list --repo . --type all
```

`No live comments` だけを根拠にコメントなしと判断しない。
`--type all` でユーザーコメント、agent comment、live comment をまとめて確認する。
出力が空または疑わしい場合は、閉じる前に `--type user` でも確認する。

Herdr で今回のレビュー用 Hunk tab を使った場合も、コメント回収とユーザーへの整理提示が終わるまで閉じない。

閉じる場合:

```sh
herdr tab close <hunk-tab-id>
```

閉じてよいのは、この skill が今回のレビュー用に作成した tab、またはユーザーが今回のレビュー用に利用を許可した Hunk 専用 tab だけである。
別 diff や別用途の既存 tab は、確認なしに閉じない。
close に失敗してもコメント整理は続け、閉じられなかった tab / pane ID と理由を報告する。

コメントがある場合は、原文、file / line / hunk 情報、推定分類を保持して整理する。
分類は断定せず、`対応必須?` / `確認必要` / `見送り候補?` 程度に留める。
修正着手や commit 続行は必ずユーザー確認を挟む。

コメントが 0 件の場合も自動承認しない。
Hunk tab を開いたまま、次を確認する。

```text
Hunk コメントはありませんでした。こちらでは `--type all` でもコメントが見えていません。指摘なしとして進めてよいですか？
```

## Stale check

追加レビュー、コメント対応後の再レビュー、既存 Hunk tab の継続利用では、通常 path で Hunk session と現在 diff の file set を比較する。

```sh
"$HUNK_HUMAN_REVIEW" snapshot
```

JSON の扱い:

- `stale: false` なら同じ file set として扱ってよい。
- `stale: true` なら Hunk tab が古い可能性があるため、「既存を reload / 新規 tab を作る / 中止」を確認して止まる。
- `stale: null` または `comparable: false` なら Hunk 側 file set を確定できていない。人間に状態を説明し、reload / 新規 tab / 中止を確認して止まる。

## Stop conditions

- `hunk` がない。
- Git repo 外。
- untracked を `git add -N` できず、作業対象 path も特定できない。
- `git add -N` 後も未ステージ差分がない。
- 既存 Hunk session / tab があり、再利用・reload・新規作成の方針が未確認。
- Hunk session が見つからず、Hunk pane / terminal も確認できない。
- 人間レビュー完了待ち。
- コメント回収後、修正・commit 方針が未確認。

## Safety

- Hunk に見えていない staged をレビュー済みとして扱わない。
- 既存 Hunk session / Hunk tab を無断で reload、再利用、close しない。
- レビュー完了後に close するのは、今回使った Hunk 専用 tab だけ。
- comment / note を無断で消さない。
- agent comment を事前投入しない。
