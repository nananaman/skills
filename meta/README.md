# Meta Skills

agent skill の作成、改善、レビュー、棚卸し、APM 配布に使う skill 群です。
skill lifecycle は `skill-workbench` に集約し、APM 配布運用は別 skill として扱います。

## どの Skill を使うか

- skill・AGENTS.md・tool 指示を作成・改善する、実行比較や構造探索を行う、またはレビュー・監査する → [`skill-workbench`](./skill-workbench/SKILL.md)
- APM の参照方式、install、dotfiles 連携を扱う → [`apm-usage`](./apm-usage/SKILL.md)
- global / project-local APM dependency を最新化する → [`update-skills`](./update-skills/SKILL.md)
- 本人・所属組織が管理するスキルを日次等の実務振り返りから保守する → [`skill-maintenance`](./skill-maintenance/SKILL.md)

## 典型フロー

1. `skill-maintenance` で許可された実務の事例と仮説を整理し、必要な候補を `skill-workbench` の実行・診断・編集・検証へ渡す。候補を保存し、必要なら廃止・統合を含む構造探索へ進む。
2. ユーザーが明示依頼した場合だけ commit / push / 参照方式に応じた参照先または SHA pin の更新 / `apm install -g` に進む。

## Skill 一覧

- **[`skill-maintenance`](./skill-maintenance/SKILL.md)** — 許可された実務入力の収集・再開から事例整理・候補評価までをつなぐ。
  - Use when: 本人・所属組織が管理するスキルの定期保守、未処理事例の持越し、評価候補の選別
  - Type: `model-invoked`
- **[`apm-usage`](./apm-usage/SKILL.md)** — APM で agent skill を管理・更新する手順を確認する。
  - Use when: apm.yml 更新、参照方式（path / SHA pin）の確認、global install / dotfiles 連携
  - Type: `model-invoked`
- **[`skill-workbench`](./skill-workbench/SKILL.md)** — skill・AGENTS.md・tool 指示を、実行結果に基づく更新と候補比較・構造探索で改善する。
  - Use when: skill 作成・改善、評価・診断・候補比較、統合・廃止、指示のレビュー・監査
  - Type: `model-invoked`
- **[`update-skills`](./update-skills/SKILL.md)** — APM skill dependency を最新化する。
  - Use when: apm.yml の pin drift、local 参照先の同期漏れ、複数 skill の一括更新、source-of-truth と展開先の同期確認
  - Type: `user-invoked`
