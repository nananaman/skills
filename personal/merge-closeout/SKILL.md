---
name: merge-closeout
description: PR をマージした後、local の default branch を安全に同期してから retrospective-codify を実行したいとユーザーが明示したときに使う。PR の作成・マージ、単なる pull、retrospective だけの依頼には使わない。
disable-model-invocation: true
---

# Merge Closeout

マージ後の local repository を remote の default branch と同じ commit へ同期し、今回の作業で得た再利用可能な知見を棚卸しする。

## Workflow

1. repository、current branch、dirty worktree、remote、default branch を確認する。
2. 対象 PR がマージ済みであることを、会話上のユーザー報告または GitHub 上の状態で確認する。対象 PR や repository を特定できない場合は同期せず確認する。
3. dirty changes を stash、破棄、commit せずに default branch へ切り替える。dirty changes が切り替えを妨げる場合は、変更内容を報告して停止する。
4. default branch で remote を fetch し、remote-tracking branch へ `--ff-only` で merge する。diverge している場合は history を変更せず停止する。
5. local と remote の default branch が同じ commit を指すことを確認する。
6. `retrospective-codify` の workflow を実行し、提案を提示する。永続ファイルへの書き出しは、同 skill の承認 gate に従う。

## Safety

- dirty changes と unrelated changes を保存したまま進める。
- stash、reset、clean、rebase、force push、branch 削除は行わない。
- 同期または retrospective の一方が未完了なら、完了したとは報告しない。

## Completion

次の両方をユーザーへ報告した時点で完了する。

- local と remote の default branch の同期結果
- `retrospective-codify` による提案、または採用候補がないという結論
