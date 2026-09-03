---
name: chouge-git-wt
description: 新しい作業を始める前に、working tree に既存の差分がないか確認する。見覚えのない差分がある場合は git worktree で作業ディレクトリを分離し、破壊や衝突を避ける。commit・branch 命名・PR 運用などの一般的な Git 規約は `chouge-git` を使う。
---

# Chouge Git Worktree

新しい作業を始める前に一度使う。目的は、他 agent や自分の別作業がすでに残した差分を、上書きや `git clean` 等で壊さないこと。同じ作業を続けている間(自分がその場で作った差分を編集し続ける間)は再確認しなくてよい。

## 作業の振り分け

`git status` と `git log` で現在の branch と working tree を確認してから振り分ける。

| 分岐 | 起動条件 | 完了条件 |
| --- | --- | --- |
| そのまま作業 | working tree の既存差分が、今回の作業で自分が作ったと確認できるもの(またはない) | 現在の branch が目的の変更に合っている、または合わせた |
| worktree で分離 | 今回の作業で自分が作ったのではない uncommitted な変更や commit が既に working tree にある(他 agent や自分の別作業の途中成果である可能性がある) | 対象 branch 用の git worktree を作成し、その中で作業を開始した |

## そのまま作業

- 現在の branch が default branch や別目的の branch の場合は、変更を混ぜずに新規 branch を作ってから作業する(working tree はクリーンなので `git checkout -b <branch>` でよく、worktree 分離は不要)。

## worktree で分離

- 特定 tool 専用の worktree 機能(例: Claude Code の `EnterWorktree`、`gwq` などの外部ツール)には依存せず、plain な `git worktree` コマンドを使う。
- worktree は repository の外側、`<repository の親ディレクトリ>/<repository名>.worktrees/<branch>` に作成する。repository 直下や `.git/` 配下には作成しない。
- 既存の差分には触れない。commit、stash、`git clean` などを行わない。
- 実行前に本体 repository のルートへ移動する: `cd "$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")"`。すでに(この skill で作成した)worktree の中にいる場合、`git rev-parse --show-toplevel` はその worktree 自身を返し入れ子になるため使わない。
- 新規 branch を作る場合: 最新の origin を取得したうえで作る。ローカルの `<default-branch>` は古い可能性があるため使わない。
  - `git fetch origin <default-branch>`
  - `git worktree add ../<repo>.worktrees/<branch> -b <branch> origin/<default-branch>`
- 既存 branch に切り替える場合(他所でチェックアウトされていない branch に限る。分離元の branch 自身は必ず他所でチェックアウトされているため対象にならない): `git worktree add ../<repo>.worktrees/<branch> <branch>`
- 一覧: `git worktree list`
- 移動: branch 名の変更に合わせる場合などは `git worktree move <旧パス> <新パス>` を使う。移動後は、絶対パスを焼き込んだ生成物(Python の `.venv` 等)が旧パスを指して壊れるため作り直す。
- 削除: 変更を commit または破棄したうえで `git worktree remove ../<repo>.worktrees/<branch>`。未commit/未追跡ファイルが残っていると失敗するため、意図して破棄する場合だけ `--force` を付ける。不要な branch は `git branch -d <branch>` で削除する。

## 関連

commit、branch 命名、PR 運用などの一般的な Git 規約は `chouge-git` skill に従う。
