---
name: chouge-git
description: Git 操作、commit、branch、push、PR を扱うときに、明文化された project 規則を優先しつつ chouge 個人の Git/GitHub 運用規約を適用する。
---

# Chouge Git

chouge 個人の Git/GitHub 運用デフォルトを定める。
この skill は、人間にも agent にも共通する Git の規約・規則・使い方だけを扱う。

## 原則

Git / GitHub 運用に関する指示が複数ある場合は、次の順で優先する。

1. ユーザーの明示指示
2. 対象 project に明文化された規則
3. この `chouge-git` skill

明文化された project 規則とこの skill が矛盾する場合は、project 規則を優先する。
ただし、PR の ready 作成は Pull Request 節の安全規則を優先し、project 規則だけでは ready PR にしない。
明文化された規則がない場合は、既存 commit、branch 名、PR title から暗黙の慣習を推測して従う必要はない。

## Project Rules

Git / GitHub 運用に関しては、対象 project に明文化された規則をこの skill より優先する。
ただし、PR の ready 作成は Pull Request 節の安全規則を優先し、ユーザーの明示指示がない限り draft で作成する。

確認対象の例:

- `AGENTS.md`
- `CLAUDE.md`
- `CONTRIBUTING.md`
- `README.md`
- `.github/pull_request_template*`
- `.github/ISSUE_TEMPLATE/`
- docs 配下の開発者向け文書

既存 commit、branch 名、PR title は明文化された規則として扱わない。

## Commit Message

project に明文化された commit 規約がある場合はそれに従う。
ない場合は Conventional Commits に沿う。

- subject は日本語の説明形にする。
- scope は任意。
- breaking change は Conventional Commits の `!` または `BREAKING CHANGE:` で示す。

## Commit Granularity

1 commit は 1 つの目的にまとめる。
unrelated changes を同じ commit に混ぜない。
format-only change や generated file の大規模差分は、可能なら実質変更と分ける。

## Commit Body

subject だけで意図や影響が伝わらない場合は body を書く。
body では「何を変えたか」よりも「なぜそうしたか」を優先する。

## Branch Naming

project に明文化された branch 命名規則がある場合はそれに従う。
ない場合は次の形式を使う。

```text
{type}/{category}/{description}
```

小さい repository や category が自然に決まらない場合は、短縮形を使ってよい。

```text
{type}/{description}
```

- `type` は `feature`、`fix`、`docs`、`chore` など、変更目的を表す短い英語にする。
- `category` は repository ごとの自然な領域名にする。
- `description` は英小文字 kebab-case にする。

## Pull Request

- PR は通常 draft で作成する。ready PR で作成するのは、ユーザーが明示的に ready PR 作成を指示した場合だけにする。
- project 規則が ready PR 作成を求めていても、ユーザーの明示指示がなければ draft で作成する。ready 化は人間の確認後に行う。
- PR title / body / reviewer 向け説明は、project に明文化された言語指定がない限り日本語で書く。
- PR body は実際の diff、commit、テスト状況と一致させる。
- project に PR template がある場合は、その構成を優先する。

## History Rewrite

- `main`、release branch、他者と共有している branch では history rewrite しない。
- 個人作業 branch で commit 整理が必要な場合のみ、rebase / amend / squash を使ってよい。
- force push が必要な場合は、`--force` ではなく `--force-with-lease` を使う。

## Safety

- `git reset --hard` と `git clean` は、実行前に削除対象を確認する。
