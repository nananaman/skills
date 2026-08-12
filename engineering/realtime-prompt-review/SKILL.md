---
name: realtime-prompt-review
description: OpenAI Realtime API の音声 agent で、言語切替、冗長・平板な発話、咳・無音・背景音への誤応答、数字や固有名詞の読み上げ、tool 誤選択、会話 flow や human escalation の逸脱など、観測済みの症状から system prompt を診断・改善する。汎用 agent prompt、Realtime API の接続・音声設定・実装障害、症状のない新規 prompt 作成には使わない。
disable-model-invocation: true
---

OpenAI Realtime API 用 system prompt の変更を、観測された音声対話の症状と検証可能な仮説に結び付ける。
公式 Realtime model guide の型を一律に当てはめず、model family と症状に必要な介入だけを選ぶ。

## 作業の振り分け

| 分岐 | 起動条件 | 完了条件 |
| --- | --- | --- |
| 診断 | 原因分析、技法選定、レビューだけを求められた | 症状、候補の採否、根拠、副作用、検証案を返し、prompt は変更していない |
| 改善 | prompt の改訂または差分を求められた | 保存対象を維持した最小差分と、候補の採否、副作用、検証結果または評価計画を返した |

新規 voice agent の要件整理やゼロからの prompt 作成は扱わない。
汎用的な agent-facing prompt の契約だけを診断する依頼は `improve-agent-prompt` を使う。
Realtime の接続方式、VAD、model、voice、`speed` parameter、tool schema や handler の実装変更は別の API・実装作業として分ける。

## 必要な根拠

次を prompt、設定、session log、transcript、録音、tool trace、利用者の報告から確認する。

- 正式な system prompt と、実際に渡された tool 一覧・description。
- 観測された挙動、期待する挙動、影響、発生条件。再現記録がなければ利用者の報告と明記する。
- model snapshot、音声入力条件、言語、関連する session 設定。Realtime 2 では `reasoning.effort` も確認する。
- responder–thinker 構成なら、外部 supervisor / thinker の出力と、実際の responder 発話の対応。
- 維持する role、業務規則、安全・確認・escalation、出力言語、会話 flow。

正式な prompt を取得できない場合は推測で再構成せず、診断可能な範囲と必要な最小資料を返して止まる。
prompt と runtime のどちらが原因か未確定なら、原因を断定しない。

## 手順

1. 症状を一つずつ観測可能な形にする。
   - 「不自然」のような評価を、発話長、言語切替、誤った tool call、無音への応答、状態遷移などへ分解する。
   - 正常な例と失敗例を分け、発生条件と頻度を記録する。
2. model family、保存対象、変更可能な層を固定する。
   - `gpt-realtime-2` では Realtime 2 固有候補を評価する。`gpt-realtime-1.5` では共通候補を使う。別 snapshot へ適用する場合は要評価とする。
   - prompt の明示契約を列挙し、tool schema、VAD、client playback など prompt 外の問題を分離する。
3. [`references/symptom-playbook.md`](./references/symptom-playbook.md) を読み、症状ごとに主要候補を比較する。
   - 候補を採用、不採用、要評価へ分類する。
   - 採用条件、期待する作用、調整方法、副作用を記録する。
   - 最初の原因仮説に合う候補だけでなく、より直接的な介入と「変更しない」を検討する。
4. 診断では変更案までを返す。改善では一つの原因仮説につき最小の prompt 差分を作る。
   - 矛盾を除き、短い bullet と焦点を絞った section を使う。
   - sample phrase は意図する発話の anchor として使い、固定句化の危険と Variety の必要性を評価する。
   - 症状がない section を skeleton に合わせて追加しない。
5. [`references/evaluation.md`](./references/evaluation.md) に従い、変更した介入を個別に比較する。
   - 実行できる場合は baseline と candidate を同じ入力条件で評価する。
   - 静的レビューだけなら改善済みとせず、未検証の仮説として返す。

## 変更の境界

- tool 名・description・利用可能性の矛盾は指摘するが、tool schema や実装は依頼範囲に含まれない限り変更しない。
- `reasoning.effort`、VAD、model、voice など session 設定の変更は、prompt 候補と分けて提案・検証する。
- WRITE tool の確認、本人確認、規制、安全、escalation は簡潔さや自動化のために弱めない。
- dynamic conversation flow は `session.update` と tool list の実装協調が確認できる場合だけ候補にする。
- prompt へ秘密、個人情報、実行時に取得すべき動的データを埋め込まない。
- API 呼び出しや有料評価は、依頼で許可され利用可能な認証情報と費用条件がある場合だけ実行する。

## 出力

```md
## 診断
- 対象と観測根拠:
- 保存対象:
- prompt 外へ分離した事項:

## 技法の採否
| 症状 | 候補 | 採否 | 適用条件と根拠 | 期待する作用 | 副作用・不採用理由 |
| --- | --- | --- | --- | --- | --- |

## 変更
<診断では変更方針、改善では最小差分または改訂 prompt>

## 検証
- baseline と candidate:
- scenario と評価指標:
- 結果:
- 未検証事項と次の最小行動:
```

すべての主要症状に採用、不採用、要評価のいずれかが付き、採用した変更ごとに副作用と検証方法が対応したら完了する。
