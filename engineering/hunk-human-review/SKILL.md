---
name: hunk-human-review
description: commit 前に Hunk TUI で未ステージ差分を人間レビュー依頼し、進行中の Hunk 人間レビューで「レビュー完了」と言われたらコメントを回収する。Hunk で人間に確認してもらう、commit 前に人間へ見せる依頼で使う。詳細コードレビュー、修正、commit、PR 作成、単なる「レビューして」では使わない。
---

# Hunk Human Review

commit 前に、Hunk TUI で未ステージ差分を人間へレビュー依頼する workflow。
この skill は Hunk session を用意し、軽いサマリとレビュー手順を提示し、レビュー完了後に Hunk コメントを回収して対応一覧に整理する。

## Scope

対象は **未ステージ差分** だけ。
未追跡ファイルがある場合は、内容を staged にせず Hunk で見えるようにするため、preflight で `git add -N` を自動実行して intent-to-add にする。

この skill はしない:

- 詳細コードレビュー
- agent inline comment の事前投入
- 修正作業
- commit 実行
- PR 作成
- 既存 Hunk session の無断 reload / 再利用
- 人間レビュー完了の推測

必要なら別 skill に委譲する。

- 詳細レビュー: `review-diff-code`
- Git / commit: `chouge-git`
- PR: `create-pr`
- Herdr pane 操作: `herdr`

## Workflow

1. preflight を行う。
2. 既存 Hunk session を確認する。
3. Hunk を開く。
   - Herdr-managed pane なら `herdr` skill を使い、同じ workspace の別 tab に `--no-focus` で開く。
   - Herdr 外なら、ユーザーへ別 terminal で `hunk diff` を開く手順を提示する。
4. Hunk session を確認し、軽い変更サマリを作る。
5. レビュー依頼文を提示して停止する。
6. ユーザーがレビュー完了を伝えたら、Hunk コメントを回収する。
7. コメントを原文つきで整理し、修正・commit へ進む前にユーザー確認を取る。

## Preflight

実行前に確認する。

```sh
command -v hunk
git rev-parse --show-toplevel
git status --short
# untracked files があれば、内容を stage せず intent-to-add にする
UNTRACKED_PATHS=$(mktemp)
git ls-files --others --exclude-standard -z > "$UNTRACKED_PATHS"
if [ -s "$UNTRACKED_PATHS" ]; then
  git add -N --pathspec-from-file="$UNTRACKED_PATHS" --pathspec-file-nul
fi
git diff --quiet
```

扱い:

- `hunk` がない: 止める。
- Git repo 外: 止める。
- untracked files がある: NUL 区切りで path を列挙し、`git add -N --pathspec-from-file=<file> --pathspec-file-nul` を自動実行して、Hunk の未ステージ差分に含める。
  - path 列挙は `git ls-files --others --exclude-standard -z` を使う。`git status --short` の表示を手で parse しない。
  - これは intent-to-add であり、内容は staged しない。
  - intent-to-add した path set を保持し、実行後に `git status --short` と `git diff --quiet` を再確認する。
- 未ステージ差分がない: 止める。
  - staged だけの場合は「Hunk のレビュー対象なし」として止める。
- staged 変更がある: 止めずに依頼文へ「staged は Hunk 対象外」と明示する。

staged / untracked の有無は `git status --short` で確認する。
この skill の初期版では staged diff review は扱わない。

## 既存 Hunk session

既存 session は勝手に触らない。

```sh
hunk session get --repo .
```

session が見つかったら、次を伝えて確認する。

- 既存 Hunk session がある。
- それを使ってよいか。
- 許可なしに `reload`、comment 削除、note 変更をしない。

許可がない場合は停止する。

## Hunk を開く

### Herdr-managed pane の場合

`HERDR_ENV=1` なら `herdr` skill を使う。
Herdr の guardrail と workspace / tab / pane 操作は `herdr` skill に従う。

基本方針:

- repo root を確認する。
- `herdr pane list` で focused pane を確認し、その `workspace_id` を `<current-workspace-id>` として使う。
- `herdr workspace list` と `herdr tab list --workspace <current-workspace-id>` で現在 workspace と既存 `hunk-review` tab を確認する。
  - 既に存在する場合は、作成前にユーザーへ「既存 tab を使う / 新規 tab を作る / 中止」を確認して止まる。
  - 許可なしに既存 tab を再利用、close、rename しない。
- 既存 tab がない、またはユーザーが新規作成を許可した場合だけ、`herdr tab create --workspace <current-workspace-id> --label "hunk-review" --no-focus` で Hunk 専用 tab を作る。
- 作成または利用許可された root pane で `cd <repo-root> && hunk diff` を実行する。
- agent の現在 tab / pane の focus は奪わない。
- 依頼文で「同じ workspace の `hunk-review` tab の Hunk を見てください」と案内する。

別 tab を使う理由:

- 既存 pane をさらに分割すると Hunk の表示幅が狭くなり、diff review が読みづらい。
- workspace を増やすより、同じ project context 内の tab として開く方が文脈が散らばりにくい。
- tab を分けると、Hunk TUI を十分な幅で開きつつ agent の作業 pane を維持できる。

例:

```sh
CURRENT_WORKSPACE=$(herdr pane list \
  | python3 -c 'import sys,json; panes=json.load(sys.stdin)["result"]["panes"]; print(next(p["workspace_id"] for p in panes if p.get("focused")))')
herdr workspace list
herdr tab list --workspace "$CURRENT_WORKSPACE"
# 既存 hunk-review tab が表示されたら、ここで止めてユーザーに確認する。
# 既存 tab がない、または新規作成の許可を得た場合だけ create する。
HUNK_PANE=$(herdr tab create --workspace "$CURRENT_WORKSPACE" --label "hunk-review" --no-focus \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["result"]["root_pane"]["pane_id"])')
herdr pane run "$HUNK_PANE" "cd <repo-root> && hunk diff"
```

既に `hunk-review` tab や同 repo の Hunk session がある場合は、勝手に再利用・close・reload しない。
ユーザーに既存のものを使うか、新規 tab を作るか確認する。

### Herdr 外の場合

自動 pane 操作はしない。
ユーザーに次を依頼して停止する。

```sh
hunk diff
```

ユーザーが Hunk を開いたことを伝えたら、session 確認へ進む。

## Hunk session 確認

Hunk を開いた後に確認する。
Hunk 起動直後は session 登録に少し時間がかかることがあるため、見つからない場合は即失敗扱いにせず、Hunk pane / terminal が開いているか確認して短く再試行する。

```sh
hunk session list
hunk session get --repo .
hunk session review --repo . --json
```

`review --json` はファイルと hunk 構造を見るために使う。
raw patch は通常取らない。
本当に必要なときだけ使う。

```sh
hunk session review --repo . --include-patch --json
```

## 変更サマリ

軽いサマリだけ作る。

使ってよい情報:

- `git status --short`
- `git diff --stat`
- `hunk session review --repo . --json`

しないこと:

- 詳細レビュー
- 問題指摘
- agent comment の投入
- raw patch 前提の深掘り

## レビュー依頼文

人間へ次の形式で提示し、ここで停止する。

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

Herdr 環境では、同じ workspace の `hunk-review` tab の Hunk を見てください。
Herdr 外で開いた場合は、別 terminal の Hunk を見てください。
必要な指摘は Hunk 上で `c` note として残してください。

終わったら「レビュー完了」と教えてください。

### 次の動き

レビュー完了後、Hunk コメントを回収して対応一覧に整理します。
修正や commit は確認後に進めます。
```

見てほしい観点は diff の内容から 2〜4 点に絞る。
詳細な指摘ではなく、reviewer が見るべき観点にする。

## レビュー完了後

ユーザーが「レビュー完了」と伝えたらコメントを回収する。

```sh
hunk session comment list --repo .
```

### コメントがある場合

コメントごとに次を保持して整理する。

- 原文
- file / line / hunk 情報
- 推定分類
- confidence または根拠

分類は断定しない。

- `対応必須?`: 明確な修正指示に見える。
- `確認必要`: 質問、曖昧な指摘、意図確認が必要。
- `見送り候補?`: 好み、任意改善、今回 scope 外に見える。

最終分類、修正着手、commit 続行は必ずユーザー確認を挟む。

### コメントが 0 件の場合

自動承認扱いしない。
次を確認する。

```text
Hunk コメントはありませんでした。指摘なしとして進めてよいですか？
```

## 停止条件

以下では止める。

- `hunk` がない。
- Git repo 外。
- `git add -N` 後も未ステージ差分がない。
- 既存 Hunk session があり、再利用許可がない。
- Hunk session が短い再試行後も作れない / 見つからない。
  - preflight で `git add -N` した path があれば、intent-to-add が index に残っていることを報告する。
  - ユーザーが戻したい場合だけ `git reset -q --pathspec-from-file=<recorded-path-file> --pathspec-file-nul` を提案または確認後に実行する。
- 人間レビュー完了待ち。
- コメント回収後、修正・commit 方針が未確認。

## Safety

- 既存 Hunk session / `hunk-review` tab を無断で `reload`、再利用、close しない。
- comment / note を無断で消さない。
- agent comment を事前投入しない。
- Hunk に見えていない staged をレビュー済みとして扱わない。
- untracked は `git add -N` 後に Hunk に見える状態だけをレビュー対象にする。
- `git add -N` した後にレビュー依頼へ進めず止まる場合は、intent-to-add が残ることを隠さない。戻す操作はユーザー確認後だけ行う。
- コメント 0 件を承認とみなさない。
