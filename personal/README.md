# Personal Skills

chouge 個人の Git/GitHub 運用や変更履歴作成に使う skill 群です。
project の明文化された規則を優先しつつ、個人のデフォルト運用を補います。

## どの Skill を使うか

- commit、branch、push、PR を扱う → [`chouge-git`](./chouge-git/SKILL.md)
- `CHANGES.md` がある repository で変更履歴を書く → [`chouge-changelog`](./chouge-changelog/SKILL.md)
- release / PR / commit 内容を変更履歴向けにまとめる → [`chouge-changelog`](./chouge-changelog/SKILL.md)

## 典型フロー

1. Git 操作や PR 作成時は `chouge-git` の運用規約を確認する。
2. `CHANGES.md` がある repository では、必要に応じて `chouge-changelog` で変更履歴を作る。
3. project 固有の `AGENTS.md` / `CLAUDE.md` がある場合は、個人規約より優先する。

## Skill 一覧

- **[`chouge-changelog`](./chouge-changelog/SKILL.md)** — CHANGES.md が存在する repository で変更履歴を書く。
  - Use when: CHANGES.md 更新、release note 下書き、PR / commit 内容の変更履歴化
  - Type: `user-invoked`
- **[`chouge-git`](./chouge-git/SKILL.md)** — chouge 個人の Git/GitHub 運用規約を適用する。
  - Use when: commit、branch、push、PR 作成・更新
  - Type: `model-invoked`
