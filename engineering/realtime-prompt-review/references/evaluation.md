# Realtime prompt の評価

## 比較単位

一つの原因仮説につき、baseline と candidate の差を一つの介入へ絞る。
model snapshot、voice、`reasoning.effort`、session 設定、tool set、入力 audio、network 条件は可能な範囲で固定する。
model migration、session setting、prompt の効果を同じ比較へ混ぜない。
非決定性があるため、重要 scenario は複数回実行し、単発成功だけで採用しない。

## Scenario

正常系、症状の再現条件、副作用を検出する反例を分ける。

| 種類 | 例 | 主な評価 |
| --- | --- | --- |
| 正常系 | 明瞭な一言語入力、標準的な依頼、tool 成功 | task 完了、latency、自然さ |
| 症状再現 | noise、code 読み上げ、複数 entity、同じ acknowledgement の連続、曖昧な intent、長 session | 対象症状の発生率 |
| 反例 | accent、side conversation、明確な呼びかけ、不要な逐字読み、WRITE tool、tool error、escalation 閾値の直前・到達後、flow の割込み | 安全契約と副作用 |

## 指標

症状に直接対応する一次指標と、退行を検出する guardrail を定義する。

- transcript: 言語、文数、必須情報、逐語一致、重複、clarification。
- audio: 発話時間、pace、対象語の発音、artifact。音声品質は transcript だけで判定しない。
- tool trace: 選択、引数、call 順、確認、preamble、error recovery。
- entity capture: field 単位の完全一致、曖昧値の保留、訂正後の再確認、既出値の再利用。
- flow trace: state、entry condition、exit condition、遷移、完了。
- Realtime 2: reasoning effort、first-audio latency、不要 preamble、長 session での current state。
- accent: target accent の安定性、明瞭度、language policy への干渉。
- long context: current authoritative source と stale transcript・summary が競合する場合の採用元。
- responder–thinker: supervisor の事実、数値、policy、必須文言、next action の保持。
- guardrail: safety、本人確認、同意、escalation、latency、task completion。

評価者の主観を使う tone や自然さは、比較前に 1–5 などの rubric と失敗例を固定する。
録音や transcript に個人情報・認証情報が含まれる場合は、保存・共有範囲を既存方針に従わせる。

## 判定

candidate は対象症状の一次指標を改善し、明示された guardrail を悪化させない場合だけ採用する。
結果が混在する場合は、語句の小変更、適用 state の限定、候補の不採用を選び、複数の新規規則を重ねない。
API 実行をしていない場合は、静的整合性と評価計画だけを報告し、品質向上を実証済みとしない。
