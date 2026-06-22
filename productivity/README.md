# Productivity Skills

汎用的な作業フロー、思考補助、引き継ぎ、学習支援に使う skill 群です。
コード作業に限らず、計画を詰める・会話を圧縮する・継続学習する場面を扱います。

## どの Skill を使うか

- 計画や設計を着手前に質問攻めして詰める → [`grill-me`](./grill-me/SKILL.md)
- 現在の会話を別 agent へ引き継げる形に圧縮する → [`handoff`](./handoff/SKILL.md)
- 現在の directory を学習 workspace として使う → [`teach`](./teach/SKILL.md)

## 典型フロー

1. 着手前に不確実性が高い場合は `grill-me` で判断分岐を解消する。
2. 作業が長くなったら `handoff` で次の agent が読める状態に圧縮する。
3. 学習目的の directory では `teach` で記録を残しながら複数セッションで進める。

## Skill 一覧

- **[`grill-me`](./grill-me/SKILL.md)** — 計画や設計を着手前に容赦なく質問して詰める。
  - Use when: plan / design の stress-test、実装前の懸念洗い出し、判断分岐の解消
  - Type: `user-invoked`
- **[`handoff`](./handoff/SKILL.md)** — 現在の会話を別の agent が引き継げる handoff document に圧縮する。
  - Use when: セッション引き継ぎ、長い会話の圧縮、別 agent への作業移管
  - Type: `user-invoked`
- **[`teach`](./teach/SKILL.md)** — 現在のディレクトリを学習 workspace として使い、複数セッションで教える。
  - Use when: 新しい概念の学習、技術・技能の継続学習、学習記録の管理
  - Type: `user-invoked`
