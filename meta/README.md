# Meta Skills

agent skill の作成、改善、レビュー、棚卸し、APM 配布に使う skill 群です。
skill lifecycle は `skill-workbench` に集約し、APM 配布運用は別 skill として扱います。

## どの Skill を使うか

- 新しい skill を作る、構造・routing・lifecycle を改善する、skill diff / 全体レビューを行う、または skill inventory を棚卸しする → [`skill-workbench`](./skill-workbench/SKILL.md)
- APM の参照方式、install、dotfiles 連携を扱う → [`apm-usage`](./apm-usage/SKILL.md)
- global / project-local APM dependency を最新化する → [`update-skills`](./update-skills/SKILL.md)
- 試行錯誤で得た知見を lint rule、skill、AGENTS.md rule へ固定する → [`retrospective-codify`](./retrospective-codify/SKILL.md)

## 典型フロー

1. `skill-workbench` で skill を作成し、構造・routing・lifecycle を改善して、必要に応じて差分レビュー、全体レビュー、一覧の監査を行う。
2. ユーザーが明示依頼した場合だけ commit / push / 参照方式に応じた参照先または SHA pin の更新 / `apm install -g` に進む。

## Skill 一覧

- **[`apm-usage`](./apm-usage/SKILL.md)** — APM で agent skill を管理・更新する手順を確認する。
  - Use when: apm.yml 更新、参照方式（path / SHA pin）の確認、global install / dotfiles 連携
  - Type: `model-invoked`
- **[`skill-workbench`](./skill-workbench/SKILL.md)** — agent skill の作成・改善と、本文の過剰制約・振り分け・参照連鎖のレビュー・監査を扱う。
  - Use when: 改善案の提示、新規 skill 作成、構造・routing・lifecycle 改善、skill diff / 全体レビュー、skill inventory audit
  - Type: `model-invoked`
- **[`retrospective-codify`](./retrospective-codify/SKILL.md)** — 再利用可能な知見を、既存規則の削除・限定・更新や適切な設定へ固定する。
  - Use when: 明示的な retrospective / codify 依頼、skill / AGENTS.md / lint rule への知見固定
  - Type: `user-invoked`
- **[`update-skills`](./update-skills/SKILL.md)** — APM skill dependency を最新化する。
  - Use when: apm.yml の pin drift、local 参照先の同期漏れ、複数 skill の一括更新、source-of-truth と展開先の同期確認
  - Type: `user-invoked`
