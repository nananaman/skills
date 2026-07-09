# Meta Skills

agent skill の作成、改善、レビュー、棚卸し、APM 配布に使う skill 群です。
skill lifecycle は `skill-workbench` に集約し、APM 配布運用は別 skill として扱います。

## どの Skill を使うか

- 新しい skill を作る、既存 skill を改善する、skill diff / 全体レビューを行う、または skill inventory を棚卸しする → [`skill-workbench`](./skill-workbench/SKILL.md)
- APM の pin、install、dotfiles 連携を扱う → [`apm-usage`](./apm-usage/SKILL.md)
- 試行錯誤で得た知見を ast-grep rule、skill、AGENTS.md rule へ固定する → [`retrospective-codify`](./retrospective-codify/SKILL.md)

## 典型フロー

1. `skill-workbench` で skill を作成・改善し、Review diff / Review whole / Audit inventory branch で必要な gate を通す。
2. ユーザーが明示依頼した場合だけ commit / push / dotfiles の SHA pin 更新 / `apm install -g` に進む。

## Skill 一覧

- **[`apm-usage`](./apm-usage/SKILL.md)** — APM で agent skill を管理・更新する手順を確認する。
  - Use when: apm.yml 更新、SHA pin 更新、global install / dotfiles 連携
  - Type: `model-invoked`
- **[`skill-workbench`](./skill-workbench/SKILL.md)** — agent skill の作成・改善・レビュー・棚卸しを 1 つの lifecycle として扱う。
  - Use when: 新規 skill 作成、既存 skill 改善、skill diff / 全体レビュー、skill inventory audit
  - Type: `user-invoked`
- **[`retrospective-codify`](./retrospective-codify/SKILL.md)** — 試行錯誤で得た再利用可能な知見を固定する。
  - Use when: 明示的な retrospective / codify 依頼、skill / AGENTS.md / ast-grep rule への知見固定
  - Type: `user-invoked`
