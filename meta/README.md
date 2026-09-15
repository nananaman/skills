# Meta Skills

agent skill の作成、改善、レビュー、棚卸し、APM 配布に使う skill 群です。
skill lifecycle は `skill-workbench` に集約し、APM 配布運用は別 skill として扱います。

## どの Skill を使うか

- skill・AGENTS.md・tool 指示を作成・改善する、実行比較や構造探索を行う、またはレビュー・監査する → [`skill-workbench`](./skill-workbench/SKILL.md)
- APM の参照方式、install、dotfiles 連携を扱う → [`apm-usage`](./apm-usage/SKILL.md)
- global / project-local APM dependency を最新化する → [`update-skills`](./update-skills/SKILL.md)
- 試行錯誤を事例・証拠・仮説へ整理し、評価改善や決定的な設定修正へつなぐ → [`retrospective-codify`](./retrospective-codify/SKILL.md)

## 典型フロー

1. `retrospective-codify` で実務の事例と仮説を取り出し、`skill-workbench` で実行・診断・編集・検証を行う。候補を保存し、必要なら廃止・統合を含む構造探索へ進む。
2. ユーザーが明示依頼した場合だけ commit / push / 参照方式に応じた参照先または SHA pin の更新 / `apm install -g` に進む。

## Skill 一覧

- **[`apm-usage`](./apm-usage/SKILL.md)** — APM で agent skill を管理・更新する手順を確認する。
  - Use when: apm.yml 更新、参照方式（path / SHA pin）の確認、global install / dotfiles 連携
  - Type: `model-invoked`
- **[`skill-workbench`](./skill-workbench/SKILL.md)** — skill・AGENTS.md・tool 指示を、実行結果に基づく更新と候補比較・構造探索で改善する。
  - Use when: skill 作成・改善、評価・診断・候補比較、統合・廃止、指示のレビュー・監査
  - Type: `model-invoked`
- **[`retrospective-codify`](./retrospective-codify/SKILL.md)** — 実務の経験を事例・証拠・更新仮説へ整理し、評価改善へ渡す。
  - Use when: 明示的な retrospective / codify 依頼、事例・仮説の抽出、採用済み要求の反映
  - Type: `user-invoked`
- **[`update-skills`](./update-skills/SKILL.md)** — APM skill dependency を最新化する。
  - Use when: apm.yml の pin drift、local 参照先の同期漏れ、複数 skill の一括更新、source-of-truth と展開先の同期確認
  - Type: `user-invoked`
