---
name: chouge-git
description: Git操作とGitHub PRに、プロジェクトの明文化された規則を優先して個人の運用規約を適用する。
---

# Chouge Git

ユーザーの明示指示、対象projectの明文化された規則、このskillの順で適用する。
ただしready PRはユーザーが明示した場合だけ作成し、通常はdraftにする。
対象操作に関係するAGENTS.md、CONTRIBUTING、PR template等を確認する。既存の題名やbranch名から暗黙の規則を推測する必要はない。

## GitHub 操作

ローカルの作業コピーを特定できる場合は `git` と `gh` を既定にする。
GitHub connectorはユーザー指定、ローカルコピーがない場合、ghに必要な機能がない場合に使う。
ghが失敗したら実行経路と原因を診断する。

## 操作別の規則

- commit時は [コミット規約](references/commits.md) を読む。
- PR作成・更新時は [PR規約](references/pull-requests.md) を読む。

## ブランチ名

プロジェクトに明文化されたブランチ命名規則がある場合はそれに従う。
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

## 既存の作業と履歴の保護

他者の差分を上書き・stash・破棄しない。編集が衝突する場合はworktree等で分離する。
main、リリースbranch、共有branchの履歴は書き換えない。
個人作業branchの整理ではrebase・amend・squashを使える。force pushが必要なら `--force-with-lease` を使う。
`git reset --hard` と `git clean` は実行前に削除対象を確認する。
