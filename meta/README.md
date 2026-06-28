# Meta Skills

agent skill の作成、改善、レビュー、APM 配布に使う skill 群です。
作る skill と、作った skill を安全に運用するための gate を分けて扱います。

## どの Skill を使うか

- 新しい skill を作る、または既存 skill の draft を改善する → [`create-skill`](./create-skill/SKILL.md)
- skill の変更差分を commit / push / pin / install 前に確認する → [`review-diff-skill`](./review-diff-skill/SKILL.md)
- skill 全体の責務や発火条件を棚卸しする → [`review-skill`](./review-skill/SKILL.md)
- skill レビューの観点を確認する → [`reviewing-skills`](./reviewing-skills/SKILL.md)
- APM の pin、install、dotfiles 連携を扱う → [`apm-usage`](./apm-usage/SKILL.md)
- 試行錯誤で得た知見を ast-grep rule、skill、AGENTS.md rule へ固定する → [`retrospective-codify`](./retrospective-codify/SKILL.md)

## 典型フロー

1. `create-skill` でレビュー可能な draft を作る。
2. `review-diff-skill` で差分をレビューし、actionable finding を解消する。
3. ユーザーが明示依頼した場合だけ commit / push / dotfiles の SHA pin 更新 / `apm install -g` に進む。

## Skill 一覧

- **[`apm-usage`](./apm-usage/SKILL.md)** — APM で agent skill を管理・更新する手順を確認する。
  - Use when: apm.yml 更新、SHA pin 更新、global install / dotfiles 連携
  - Type: `model-invoked`
- **[`create-skill`](./create-skill/SKILL.md)** — agent skill の新規作成・既存 skill の draft 改善を行う。
  - Use when: 新規 skill 作成、既存 skill の draft 改善、配置や起動方式の整理
  - Type: `user-invoked`
- **[`review-diff-skill`](./review-diff-skill/SKILL.md)** — skill 変更 diff を配布前にレビューする。
  - Use when: skill 差分レビュー、commit / push 前確認、APM pin / install 前確認
  - Type: `user-invoked`
- **[`review-skill`](./review-skill/SKILL.md)** — skill 全体を棚卸しして構造・責務・発火条件を見直す。
  - Use when: skill の大幅変更、新規 skill の全体レビュー、責務過多や誤発火の調査
  - Type: `user-invoked`
- **[`reviewing-skills`](./reviewing-skills/SKILL.md)** — agent skill の品質をレビューする共通 rubric。
  - Use when: description / 本文整合確認、完了条件の確認、failure modes / safety の確認
  - Type: `model-invoked`
- **[`retrospective-codify`](./retrospective-codify/SKILL.md)** — 試行錯誤で得た再利用可能な知見を固定する。
  - Use when: 明示的な retrospective / codify 依頼、skill / AGENTS.md / ast-grep rule への知見固定
  - Type: `user-invoked`
