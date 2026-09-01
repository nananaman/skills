# Productivity Skills

汎用的な作業フロー、思考補助、引き継ぎ、agent prompt 改善に使う skill 群です。
コード作業に限らず、計画を詰める・会話を圧縮する・agent-facing instructions を改善する場面を扱います。

## どの Skill を使うか

- 本筋を止めずに寄り道タスクを別 tab のセッションへ切り出す → [`btw`](./btw/SKILL.md)
- 他 skill から計画・設計・PRD・Design Doc・issue を一問ずつ詰める → [`grilling`](./grilling/SKILL.md)
- ユーザーが明示的に計画や設計を質問攻めして詰めたい → [`grill-me`](./grill-me/SKILL.md)
- 現在の会話を別 agent へ引き継げる形に圧縮する → [`handoff`](./handoff/SKILL.md)
- Herdr pane 内で隣接 pane の出力確認、pane 分割、長時間 command の実行を行う → [`herdr`](./herdr/SKILL.md)
- agent が生成した静的成果物を安定 URL から確認できるようにする → [`host-artifact`](./host-artifact/SKILL.md)
- system prompt、agent instructions、tool description、AGENTS.md、skill 本文の agent-facing contract、prompt stack を診断・改善する → [`improve-agent-prompt`](./improve-agent-prompt/SKILL.md)
  - skill の新規作成・構造・routing・lifecycle は [`skill-workbench`](../meta/skill-workbench/SKILL.md) を使う

## 典型フロー

1. 他 skill から再利用する場合は `grilling` で判断分岐を一つずつ解消する。
2. ユーザーが明示的に grill を求めた場合は `grill-me` を入口にする。
3. 本筋から外れた調査や実験が出てきたら `btw` で別 tab のセッションへ切り出し、本筋はそのまま続ける。
4. 作業が長くなったら `handoff` で次の agent が読める状態に圧縮する。
5. 長時間 command や helper agent を Herdr の sibling pane に分離するときは `herdr` を使う。
6. browser で確認する静的成果物は `host-artifact` で workspace/name の安定 URL へ publish する。
7. agent-facing prompt と skill 本文の contract は `improve-agent-prompt` で preservation set を固定し、最小差分で改善する。skill の新規作成・構造・routing・lifecycle は `skill-workbench` を使う。

## Skill 一覧

- **[`btw`](./btw/SKILL.md)** — 寄り道タスクを新しい Herdr tab の別セッションへ切り出して起動する。
  - Use when: 本筋を止めずに脇道の調査・実験・別案検証を並行させる
  - Type: `user-invoked`
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
  - Type: `user-invoked`
- **[`host-artifact`](./host-artifact/SKILL.md)** — 静的成果物を workspace/name の安定 URL で publish し、Tailscale Serve または localhost から確認できるようにする。
  - Use when: HTML、画像、静的 directory のbrowser確認、他 skill が生成した成果物の配信
  - Type: `model-invoked`
- **[`improve-agent-prompt`](./improve-agent-prompt/SKILL.md)** — agent-facing prompt と skill 本文の contract を既存意図を保った最小差分で診断・改善する。
  - Use when: system prompt、agent instructions、tool description、AGENTS.md、skill 本文の agent-facing contract、prompt stack、context 配置の改善（skill の新規作成・構造・routing・lifecycle は `skill-workbench`）
  - Type: `model-invoked`
