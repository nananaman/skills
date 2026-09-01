---
name: btw
description: 本筋のセッションを止めずに、寄り道タスクを新しい Herdr tab の別セッションへ切り出して起動する。
argument-hint: "寄り道タスクの内容"
disable-model-invocation: true
---

# BTW

本筋を進めている現在のセッションから、寄り道タスクだけを新しい Herdr tab の独立した Claude Code セッションへ切り出す。
起動を報告した時点で完了とし、寄り道の成果は回収しない。人間が報告された tab を見る。

本筋そのものを次のセッションへ移す場合は `handoff` を使う。
いまの context で数手で終わる調査は、切り出さずそのまま実行する。

## 契約

- 着手前に `../herdr/SKILL.md` を読み、Herdr 操作はその契約に従う。`HERDR_ENV` が `1` でない、または server へ接続できない場合は、tab を作らず報告して止める。pane を split する前提の reference は、tab を作るこの skill では使わない。
- 新しい tab は現在の pane と同じ workspace に `--no-focus` で作る。focus は移さず、人間が見ている pane には入力しない。
- 作業ディレクトリは現在の pane の cwd と同じにする。worktree の要否は分岐先セッションが判断する。
- 引き継ぎ文書には寄り道タスクに必要な範囲だけを書く。会話全体は要約しない。
- 起動後は本筋の作業へ戻る。分岐先の出力を待たない。

## 手順

1. 寄り道タスクの目的と完了条件を確定する。引数だけで定まらない場合はユーザーに確認する。
2. 引き継ぎ文書を、分岐先のプロセスから読める一時ファイルに書く。session 固有の作業領域や sandbox 固有の一時ディレクトリは、分岐先から読めないため使わない。
3. `herdr pane current` の `workspace_id` と `cwd` を使い、`herdr tab create --workspace <workspace_id> --cwd <cwd> --label <寄り道タスク> --no-focus` で tab を作る。
4. 返った pane へ `herdr agent start <name> --kind claude --pane <id>` で agent を起動する。
   `<name>` は寄り道タスクを表す英小文字 kebab-case の短い名前にし、`herdr agent list` の live agent 名と衝突しないことを確認する。
5. `herdr agent prompt` で引き継ぎ文書のパスと依頼を渡す。完了は待たず、agent が working になったことだけ確認する。
6. tab ID、pane ID、agent 名、文書のパス、寄り道タスクの完了条件を報告する。

## 引き継ぎ文書

寄り道タスクの目的、完了条件、そのタスクに必要な背景、使うべき skill の提案を書く。
成果は分岐先の tab に残し、本筋のセッションは回収しないことを明示する。

計画、diff、issue、PR など既存の成果物はパスまたは URL で参照し、内容を複製しない。
API キー、パスワード、個人情報は伏せる。

## 失敗時

tab 作成または agent 起動に失敗した場合は、command、exit code、stderr を報告して止める。作成済みの tab は close しない。
