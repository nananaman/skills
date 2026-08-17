---
name: herdr
description: Herdr CLI による pane の観測・分割、長時間 command、agent 協調、tab や pane の操作、Hunk review のコメント回収を依頼されたときに使う。Herdr 内にいるだけの通常タスク、短い単発 command、Herdr CLI 自体の実装、承認のない既存 pane 操作では使わない。
disable-model-invocation: true
---

# Herdr

Herdr が管理する pane から、実行中の workspace、tab、pane、agent を安全に操作する。
CLI 構文は実行時の `herdr <group> --help` を正本とし、用途固有の判断だけを reference から読む。

## 契約

- 最初に `HERDR_ENV=1`、`herdr status --json`、`herdr pane current` を確認する。Herdr 外または server 接続失敗なら操作せず止める。
- workspace、tab、pane ID は stable handle として扱う。pane move 後だけ response から新しい pane ID を取得する。
- agent target は unique な live agent 名か、その agent を現在 host する pane ID に限定する。
- agent が作る補助的な作業場は現在 tab を split した pane に限り、原則 `--no-focus` で作る。
- 補助 pane の foreground が shell でなくなった、または pane が消えた場合は、承認を求めずその pane を放棄し、新しい補助 pane を作って作業を続ける。放棄した pane への入力、close、rename はしない。
- tab と workspace の作成、focus、close、attach、takeover、pane move、swap、resize、zoom、既存 pane や既存 agent への入力は、ユーザーが明示依頼した場合だけ実行する。
- 人間が見ている active pane に入力、focus 移動、close、takeover をしない。
- tab は人間が主タスクを見分ける単位とし、tab label は tab 全体の主タスク、pane label は pane 固有の役割や作業を表す。
- 現在 tab、pane、agent の通常セッション命名は自動で行わない。label や name の変更は、ユーザーが明示依頼した対象または agent が直前に作成した補助 pane と helper agent に限定する。
- pane label を自動変更できるのは、agent が直前に作成した補助 pane だけとする。人間が管理する既存 pane とその label は変更しない。
- pane の metadata report は agent integration を明示的に扱う場合だけ実行する。
- managed Hunk review pane の起動、reload、close は agent が行わない。

## 振り分け

- 隣接 pane での command 実行、出力待ち、helper agent の起動や操作では、[`references/agent-coordination.md`](references/agent-coordination.md)を読む。
- 人間が Hunk review の完了を伝えた後のコメント回収では、[`references/hunk-review.md`](references/hunk-review.md)を読む。
- workspace、tab、pane、agent の単純な list、get、read は、対象 ID を取り直して該当 group の `--help` に従う。
- 短い単発 command は通常の shell tool を使う。

複数の分岐が必要なら、該当する reference だけを読む。
Herdr CLI 自体の実装、設定、配布、更新はこの skill の対象外とし、通常の repository 調査として扱う。

## 実行後

- 実行した操作、対象 workspace、tab、pane、agent、待機条件、結果を報告する。
- command が失敗したら、command、exit code、stderr を報告し、後続の変更操作へ進まない。
- ID が見つからない場合は list、current、get で取り直し、推測で補正しない。
- wait が timeout または stalled になった場合は、対象の get と read で失敗、実行中、marker 不一致、state change 未検出を切り分ける。
- 明示依頼が必要な操作へ進む必要が生じた場合は、対象と影響を示して承認を待つ。
