# Productivity Skills

汎用的な作業フロー、思考補助、引き継ぎ、学習支援に使う skill 群です。
コード作業に限らず、計画を詰める・会話を圧縮する・継続学習する場面を扱います。

## どの Skill を使うか

- 他 skill から、計画や設計の前提、未決定事項、依存する判断を一問ずつ詰める → [`grilling`](./grilling/SKILL.md)
- ユーザーが明示的に計画や設計を質問攻めして詰めたい → [`grill-me`](./grill-me/SKILL.md)
- 現在の会話を別 agent へ引き継げる形に圧縮する → [`handoff`](./handoff/SKILL.md)
- Herdr pane 内で隣接 pane の出力確認、pane 分割、長時間 command の実行を行う → [`herdr`](./herdr/SKILL.md)
- 現在の directory を学習 workspace として使う → [`teach`](./teach/SKILL.md)

## 典型フロー

1. 他 skill から再利用する場合は `grilling` で判断分岐を一つずつ解消する。
2. ユーザーが明示的に詰めたい対象を指定した場合は `grill-me` を入口にする。
3. 作業が長くなったら `handoff` で次の agent が読める状態に圧縮する。
4. 学習目的の directory では `teach` で記録を残しながら複数セッションで進める。
5. Herdr-managed pane では `herdr` で長時間 command や helper agent を sibling pane に分離する。

## Skill 一覧

- **[`grilling`](./grilling/SKILL.md)** — 計画や設計の前提、未決定事項、依存する判断を一問ずつ詰める。
  - Use when: 他 skill から、実装前に曖昧な判断を共有理解まで詰める
  - Type: `model-invoked`
- **[`grill-me`](./grill-me/SKILL.md)** — ユーザーが明示的に詰めたい計画や設計を `grilling` session に渡す。
  - Use when: ユーザーが明示的に、計画や設計を着手前に一問ずつ詰めたい場合
  - Type: `user-invoked`
- **[`handoff`](./handoff/SKILL.md)** — 現在の会話を別の agent が引き継げる handoff document に圧縮する。
  - Use when: セッション引き継ぎ、長い会話の圧縮、別 agent への作業移管
  - Type: `user-invoked`
- **[`herdr`](./herdr/SKILL.md)** — Herdr-managed pane 内で workspace / tab / pane を操作する。
  - Use when: 隣接 pane の出力確認、pane 分割、長時間 command / helper agent 起動、出力待ち
  - Type: `model-invoked`
- **[`teach`](./teach/SKILL.md)** — 現在のディレクトリを学習 workspace として使い、複数セッションで教える。
  - Use when: 新しい概念の学習、技術・技能の継続学習、学習記録の管理
  - Type: `user-invoked`
