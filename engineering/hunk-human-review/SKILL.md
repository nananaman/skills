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

1. preflight する。
2. 既存 Hunk session / Hunk tab を確認する。
3. Hunk を開く。
4. 軽い変更サマリとレビュー方法を提示して停止する。
5. ユーザーが「レビュー完了」または同等の完了を伝えたら、Hunk コメントを回収する。
6. Herdr で今回使った Hunk 専用 tab があれば閉じる。
7. コメントを原文つきで整理し、修正・commit へ進む前にユーザー確認を取る。

## Preflight

確認するもの:

```sh
command -v hunk
git rev-parse --show-toplevel
git status --short
```

扱い:

- `hunk` がない、Git repo 外、未ステージ差分がない場合は止める。
- staged 変更がある場合は、Hunk 対象外であることをレビュー依頼文に明示する。
- untracked files がある場合は `git ls-files --others --exclude-standard -z` で列挙し、`git add -N --pathspec-from-file=<file> --pathspec-file-nul` を実行する。
  - 実行後に `git status --short` と `git diff --quiet` を確認する。
  - `git add -N` が非通常ファイル、権限、unrelated dotfiles などで失敗した場合は、作業対象として把握している新規ファイルだけに絞って再実行する。作業対象を特定できない場合は、対象 path をユーザーに確認して止まる。
  - intent-to-add した path set を保持する。途中で止まる場合は、intent-to-add が残ることを報告し、戻す操作はユーザー確認後だけ行う。

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

```md
## Hunk レビュー依頼

対象: 未ステージ差分
repo: <repo>
branch: <branch>

### 変更概要
- <3〜5行の軽いサマリ>

### 注意
- staged 変更: <あり/なし。ありなら Hunk 対象外>
- untracked files: <元はあり/なし。ありなら git add -N 済みで Hunk 対象>
- このレビューは未ステージ差分のみを対象にしています。

### 見てほしい観点
- <観点1>
- <観点2>
- <観点3>

### レビュー方法
Herdr 環境では Hunk 用 tab、Herdr 外では別 terminal の Hunk を見てください。
必要な指摘は Hunk 上で `c` note として残してください。
終わったら「レビュー完了」と教えてください。
```

変更サマリには `git status --short`、`git diff --stat`、`hunk session review --repo . --json` を使う。
詳細レビュー、問題指摘、agent comment の事前投入はしない。

## After review

ユーザーがレビュー完了を伝えたら、コメントを回収する。

```sh
hunk session comment list --repo .
```

Herdr で今回のレビュー用 Hunk tab を使った場合は、コメント回収後に閉じる。

```sh
herdr tab close <hunk-tab-id>
```

閉じてよいのは、この skill が今回のレビュー用に作成した tab、またはユーザーが今回のレビュー用に利用を許可した Hunk 専用 tab だけ。
別 diff や別用途の既存 tab は、確認なしに閉じない。
close に失敗してもコメント整理は続け、閉じられなかった tab / pane ID と理由を報告する。

コメントがある場合は、原文、file / line / hunk 情報、推定分類を保持して整理する。
分類は断定せず、`対応必須?` / `確認必要` / `見送り候補?` 程度に留める。
修正着手や commit 続行は必ずユーザー確認を挟む。

コメントが 0 件の場合も自動承認しない。

```text
Hunk コメントはありませんでした。指摘なしとして進めてよいですか？
```

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
