# Productivity Skills

汎用的な作業フロー、思考補助、引き継ぎ、学習支援、agent prompt 改善に使う skill 群です。
コード作業に限らず、計画を詰める・会話を圧縮する・継続学習する・agent-facing instructions を改善する場面を扱います。

## どの Skill を使うか

- 他 skill から計画・設計・PRD・Design Doc・issue を一問ずつ詰める → [`grilling`](./grilling/SKILL.md)
- ユーザーが明示的に計画や設計を質問攻めして詰めたい → [`grill-me`](./grill-me/SKILL.md)
- 現在の会話を別 agent へ引き継げる形に圧縮する → [`handoff`](./handoff/SKILL.md)
- Herdr pane 内で隣接 pane の出力確認、pane 分割、長時間 command の実行を行う → [`herdr`](./herdr/SKILL.md)
- 現在の directory を学習 workspace として使う → [`teach`](./teach/SKILL.md)
- system prompt、agent instructions、tool description、skill、prompt stack を診断・改善する → [`improve-agent-prompt`](./improve-agent-prompt/SKILL.md)

## 典型フロー

1. 他 skill から再利用する場合は `grilling` で判断分岐を一つずつ解消する。
2. ユーザーが明示的に grill を求めた場合は `grill-me` を入口にする。
3. 作業が長くなったら `handoff` で次の agent が読める状態に圧縮する。
4. 学習目的の directory では `teach` で記録を残しながら複数セッションで進める。
5. Herdr-managed pane では `herdr` で長時間 command や helper agent を sibling pane に分離する。
6. agent-facing prompt は `improve-agent-prompt` で preservation set を固定し、最小差分で改善する。

## Skill 一覧

- **[`grilling`](./grilling/SKILL.md)** — 計画、設計、PRD、Design Doc、issue を共有理解に到達するまで一問ずつ詰める。
  - Use when: 他 skill から曖昧さ、未決定、依存する判断を解消する
  - Type: `model-invoked`
- **[`grill-me`](./grill-me/SKILL.md)** — ユーザーが明示的に grill したい計画や設計を `grilling` session に渡す。
  - Use when: plan / design の stress-test、実装前の懸念洗い出し、判断分岐の解消
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
- **[`improve-agent-prompt`](./improve-agent-prompt/SKILL.md)** — agent-facing prompt を既存意図を保った最小差分で診断・改善する。
  - Use when: system prompt、agent instructions、tool description、AGENTS.md、skill、prompt stack の改善、明示された対象モデルへの prompt 適応
  - Type: `model-invoked`
