---
name: skill-workbench
description: agent skill の新規作成、構造・routing・lifecycle の改善、diff / 全体レビュー、inventory 棚卸しを扱う。skill 本文だけの agent-facing prompt contract の診断・最小差分改善は improve-agent-prompt を使う。
disable-model-invocation: true
---

agent skill の lifecycle workbench。
目的は、agent の探索手順を固定することではなく、skill の outcome、判断境界、必要な evidence、検証方法を安定させること。

## Branch Router

最初に対象 branch を 1 つ選ぶ。
複数 branch が必要なら、完了条件を混ぜずに順番に処理する。

| Branch | 使う場面 | 完了条件 |
| --- | --- | --- |
| Create / Improve | 新規 skill、または既存 skill の構造・routing・lifecycle を含む改善 | 変更を作り、適切な review branch で actionable finding が残っていない |
| Review diff | skill 関連 diff の regression 確認 | skip、または evidence 付き review result を返した |
| Review whole | 新規・大幅変更・高頻度・誤作動歴・責務過多の skill の全体確認 | skill 全体と必要な evidence から accepted / rejected finding を分けた |
| Audit inventory | inventory の routing conflict、重複、粒度、sprawl / sediment の横断確認 | cluster、findings、推奨順、安全確認を報告した |

## Invariants

- `SKILL.md` は必要な情報へ到達する軽量な guide にする。詳細は該当 branch だけが reference から読む。
- 固定するのは outcome、authority / safety boundary、必要な evidence、検証方法、branch-level completion である。探索順序は、誤終了や危険を防ぐ場合だけ固定する。
- description は skill 読み込み前の routing interface として扱い、本文の要約にしない。
- finding は対象本文または実行 evidence で確認でき、action 可能なものだけ accepted にする。
- commit、push、APM pin 更新、install は、ユーザーの明示依頼がない限り実行しない。

## Create / Improve

1. 対象 skill の outcome、positive / negative routing、authority / safety boundary、evidence、completion、project 固有か汎用かを確認する。
   skill 本文だけの agent-facing prompt contract を最小差分で直す依頼は `improve-agent-prompt` に渡す。
2. 既存 skill の改善では、routing、safety / permission gate、completion、output、failure handling を preservation set として固定する。
3. 新規 skill または責務変更では近接 skill を確認する。横断判断が必要なら Audit inventory を先に行う。
4. `references/design-principles.md` を読み、本文、reference、asset、script、別 skill の境界を決めて変更する。
5. routing が難しい、問題が再発する、または客観評価できる場合だけ `references/eval-loop.md` を使う。
6. 大幅変更は Review whole、それ以外の変更は Review diff を実行し、accepted finding を解消する。

## Review diff

1. tracked / untracked を含む skill 関連 diff と preservation set を確認する。
2. `references/review-protocol.md` を読み、変更された契約に関係する rubric と check だけを選ぶ。
3. 新規 skill、model-invoked description、高頻度・誤作動歴のある skill、責務や主要 workflow の変更は Review whole へ escalate する。
4. protocol の interface で skip または review result を報告する。

## Review whole

1. 対象 skill、直接関係する resources、README 導線を読む。
2. `references/review-protocol.md` を読み、Static contract check と、risk に応じた smoke check を行う。
3. routing、責務、information hierarchy、authority / safety、completion を全体として評価する。
4. accepted finding を修正した場合は Review diff で regression を確認し、protocol の interface で報告する。

## Audit inventory

`references/audit-protocol.md` を読み、source of truth を確認してから inventory と必要な cluster だけを調べる。
worker の finding は対象本文で検証し、protocol の interface で報告する。

## Safety

- destructive deletion、rename、統合はユーザーが明示した場合だけ実行する。
- 永続ファイルへ失敗パターン台帳を書く場合は、ユーザーに確認する。確認がない場合は session 内で管理する。
