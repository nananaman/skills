# Productivity Skills

汎用的な作業フロー、思考補助、引き継ぎ、agent prompt 改善に使う skill 群です。
コード作業に限らず、計画を詰める・会話を圧縮する・agent-facing instructions を改善する場面を扱います。

## どの Skill を使うか

- 計画・設計・PRD・Design Doc・issue を一問ずつ詰める → [`grilling`](./grilling/SKILL.md)
- 現在の会話を別 agent へ引き継げる形に圧縮する → [`handoff`](./handoff/SKILL.md)
- AGENTS.md・tool 指示・skill を改善する → Meta の [`skill-workbench`](../meta/skill-workbench/SKILL.md)

## 典型フロー

1. 明示的な依頼や他 skill からの再利用では、`grilling` で判断分岐を一つずつ解消する。
2. 作業が長くなったら `handoff` で次の agent が読める状態に圧縮する。
3. agent向け指示の改善は Meta の `skill-workbench` で実行比較・構造探索を行う。

## Skill 一覧

- **[`grilling`](./grilling/SKILL.md)** — 計画、設計、PRD、Design Doc、issue を共有理解に到達するまで一問ずつ詰める。
  - Use when: 計画や設計の明示的な検討依頼、他 skill からの曖昧さ・未決定・依存する判断の解消
  - Type: `model-invoked`
- **[`handoff`](./handoff/SKILL.md)** — 現在の会話を別の agent が引き継げる handoff document に圧縮する。
  - Use when: セッション引き継ぎ、長い会話の圧縮、別 agent への作業移管
  - Type: `user-invoked`
