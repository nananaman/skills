# Personal Skills

chouge 個人の Git/GitHub 運用や変更履歴作成に使う skill 群です。
project の明文化された規則を優先しつつ、個人のデフォルト運用を補います。

## どの Skill を使うか

- commit、branch、push、PR を扱う → [`chouge-git`](./chouge-git/SKILL.md)
- PR マージ後に default branch の同期と retrospective をまとめて行う → [`merge-closeout`](./merge-closeout/SKILL.md)
- `CHANGES.md` がある repository で変更履歴を書く → [`chouge-changelog`](./chouge-changelog/SKILL.md)
- release / PR / commit 内容を変更履歴向けにまとめる → [`chouge-changelog`](./chouge-changelog/SKILL.md)

## 作業の進め方

Git操作・PR作成ではchouge-gitを使う。既存差分を守り、対象projectの明文化された規則を優先する。
PRマージ後の同期と振り返りを明示依頼された場合はmerge-closeout、変更履歴の更新にはchouge-changelogを使う。

## Skill 一覧

- **[`chouge-changelog`](./chouge-changelog/SKILL.md)** — 既存の CHANGES.md を更新する。新規作成は明示依頼時に行う。
  - Use when: CHANGES.md 更新、release note 下書き、PR / commit 内容の変更履歴化
  - Type: `model-invoked`
- **[`chouge-git`](./chouge-git/SKILL.md)** — chouge 個人の Git/GitHub 運用規約を適用する。
  - Use when: commit、branch、push、PR 作成・更新
  - Type: `model-invoked`
- **[`merge-closeout`](./merge-closeout/SKILL.md)** — PR マージ後の default branch 同期と retrospective を一度に行う。
  - Use when: PR マージ後の local 同期と知見の棚卸し
  - Type: `user-invoked`
