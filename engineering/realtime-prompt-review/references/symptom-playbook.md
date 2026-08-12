# 症状から介入候補を選ぶ

現行 model と model 別判断の主要根拠は OpenAI API docs の [Using realtime models](https://developers.openai.com/api/docs/guides/realtime-models-prompting)（2026-08-12 確認）。
Cookbook の [Realtime Prompting Guide](https://developers.openai.com/cookbook/examples/realtime_prompting_guide)（2026-02-25 公開、2026-08-12 確認）は `gpt-realtime-1.5` にも適用される音声固有パターンの補助根拠とする。
text-only、chained speech pipeline、明記されていない snapshot への一般化は要評価とする。

## Model の振り分け

| Model | 開く候補 | 注意 |
| --- | --- | --- |
| `gpt-realtime-2` | 共通台帳と Realtime 2 固有台帳 | reasoning、既定 preamble、entity capture、long-session state を評価する |
| `gpt-realtime-1.5` | 共通台帳 | Realtime 2 固有の挙動や設定を転用しない |
| それ以外・不明 | 共通台帳を要評価として参照 | snapshot を取得できるまで model 固有の変更を採用しない |

## 共通の診断

まず prompt 内の曖昧さ、重複、矛盾、長い paragraph、非テキスト的な条件式を確認する。
小さな語句差で挙動が変わりうるため、複数介入を同時に入れず、症状に直接対応する bullet を優先する。
大文字強調は重要規則の見落としが観測された場合の候補であり、全面的な大文字化は優先度を失わせるため採用しない。

## 症状別台帳

| 観測症状 | 主要候補 | 採用条件と調整 | 危険・不採用条件 | 検証可能な変化 |
| --- | --- | --- | --- | --- |
| role、persona、task scope がずれる | Role & Objective を明示 | role または完了状態が曖昧。identity と成功条件を短く固定する | 業務規則の欠落は role 文だけでは直らない | scope 外応答率、role 違反率 |
| 平板、冗長、turn ごとに tone が揺れる | Personality & Tone、Length、Pacing | warmth、formality、既定の発話長、cadence のうち症状に関係する軸だけ指定 | regulated domain で演出が精度を損なう場合は neutral precision を優先。`speed` parameter の再生速度問題とは分ける | 発話秒数、文数、tone rubric |
| 外部 supervisor / thinker の応答後だけ発話が長い、robotic、音声向きでない | Rephrase Supervisor contract | responder–thinker 構成で、thinker の内容を短く自然な speech-first 表現へ変換する | Realtime model が直接回答する場合や verbatim 出力には不採用。事実、数値、policy、必須文言、next action の欠落・意味変更が副作用 | 発話時間、自然さ、必須情報の保持率 |
| noisy / multilingual input や accent で出力言語が切り替わる | Language Constraint、language と accent の分離 | 出力言語が固定要件で、意図しない切替が観測された。accent を言語選択の根拠にしない | 通訳や利用者言語追従が要件なら固定しない | 意図しない言語 turn の比率、accent 別の言語維持率 |
| acknowledgement が同じで robotic | Variety rule、複数の sample phrase | 同一表現の反復が観測された。意味を保った言い換えを要求する | 法定文言、本人確認、同意文は変形させない | 連続 turn の重複率、必須文言一致率 |
| 固有名詞・技術語の発音を誤る | Reference Pronunciations | 誤発音が確認された短い語彙だけ phonetic hint を置く | 未観測語を大量追加しない。別 voice/model では再評価 | 対象語の発音正解率 |
| 数字、code、ID を結合・欠落して読む | character-by-character readback と再確認 | phone、2FA、order ID 等で誤りが観測された。separator と訂正後の再確認を指定 | 通常の数量まで逐字化すると冗長。機密値の録音・log 保存に注意 | 文字単位正解率、訂正後確認率、所要時間 |
| assistant 宛てだが不明瞭な発話へ見当違いに応答する | Unclear Audio rule | 明確に話しかけられたが理解不能な場合だけ、clarify または直前質問を反復する | VAD の誤検知そのものは prompt だけで解決しない | spurious response 率、clarification 成功率 |
| silence、hold music、TV、side conversation、非指向性の背景音に話しかける | 非指向性 audio と assistant 宛て unclear audio の分離 | 前者には応答せず、後者だけ clarification する | 無言で turn を終える手段は runtime・model ごとに確認する。明確な user request を無視する false negative が副作用 | 不要発話率、clarification 適合率、明確な呼びかけの応答率 |
| 音楽、humming、効果音が混ざる | 特定 artifact を抑止 | audio output に artifact が実際に観測された | 症状がなければ追加しない。client audio processing 起因なら不採用 | artifact 発生率、音声明瞭度 |
| 存在しない tool を呼ぶ、誤った tool を選ぶ | prompt と実 tool list の整合、Use when / Do not use when | tool 名、description、引数、利用条件を実際の session tools と照合する | prompt に tool を書くだけでは利用可能にならない。schema/handler defect は実装へ分離 | tool 選択 precision/recall、存在しない call 数 |
| tool 前の沈黙、不要な確認、無断 WRITE | per-tool behavior | PROACTIVE / PREAMBLE / CONFIRMATION FIRST を tool の作用ごとに分ける | global rule で READ/WRITE を一括すると安全か latency が退行。確認要件を弱めない | preamble 適合率、不要確認率、無断 write 率 |
| tool 失敗時に停止・捏造する | error / partial-result handling | 失敗が起こりうる tool に fallback、再試行上限、escalation を定義 | 成功を装う文言は禁止。無制限 retry は不採用 | failure recovery 率、捏造率、retry 回数 |
| human 要求、安全リスク、強い不満、反復失敗、scope 外でも troubleshooting を続ける | Safety & Escalation の条件、即時 handoff、発話と tool call の対応 | 閾値と即時条件を製品・安全方針から取得し、handoff の発話と tool を対応させる | 閾値を推測または弱体化しない。escalation tool が未提供なら prompt-only で解決済みにしない。過剰 escalation が副作用 | 即時 escalation 率、不要 escalation 率、閾値後の余分な turn、正しい handoff call |
| tool の長い raw string を省略・言い換える | named-field の structured output | verbatim 読み上げが必要で raw string 出力時に崩れる | prompt だけの「exactly repeat」で直らない場合は tool output schema の実装変更なので分離 | 完全一致率、欠落・混入率 |
| 必須質問を飛ばす、順序や終了条件が揺れる | Conversation Flow の state / goal / exit condition | 複数段階の業務 flow で遷移漏れが観測された | 単純対話には過剰。状態数を増やすほど prompt 長と保守負荷が増える | state coverage、遷移違反、完了率 |
| 全 state・tool の同時提示で混乱する | Dynamic Conversation Flow | app が state 遷移時に `session.update` で prompt と tools を同期できる | prompt-only 変更では採用しない。同期ずれと実装複雑性が副作用 | state 外 tool call、prompt/tool 同期 error、task 完了率 |

## Realtime 2 固有台帳

`gpt-realtime-2` でだけ候補にする。

| 観測症状 | 主要候補 | 採用条件と調整 | 危険・不採用条件 | 検証可能な変化 |
| --- | --- | --- | --- | --- |
| 単純処理でも遅い、または複雑な判断で誤る | `reasoning.effort` と Reasoning rule | 既定候補を `low` とし、単純応答は即答、multi-step・tool 判断・escalation は reasoning する。失敗コストと latency に応じ一段ずつ比較する | prompt と session 設定を同時変更しない。私的 reasoning の開示を求めない。高 effort の latency・cost が副作用 | task 成功率、first-audio latency、完了時間、cost |
| reasoning や tool call 前に沈黙する | 既定 preamble を評価し、必要な場面だけ明示 | 長い tool、multi-step、record・policy 確認で短い action update を使う | まず既定挙動を測る。軽い lookup、unclear audio、背景音では不採用。filler と体感 latency が副作用 | preamble 適合率、不要 preamble 率、first-audio latency |
| silence、hold music、TV、side conversation、非指向性 audio に発話する | `wait_for_user` による無言の no-op | 非指向性 audio と assistant 宛ての不明瞭 request を区別し、tool が実際に提供され無言で turn を終えられる場合だけ採用する | tool 未提供なら実装へ分離し、prompt-only で解決済みにしない。明確な呼びかけを無視する false negative が副作用 | `wait_for_user` 適合率、不要発話率、明確な呼びかけの応答率 |
| 「簡潔に」だけでは task ごとの長さが揺れる | task-type 別 Verbosity | direct answer、clarification、tool result、troubleshooting、escalation ごとに発話量を定義する | 全 turn を同じ文数に固定しない。説明不足や一問一答の遅延が副作用 | task 種別ごとの文数・発話時間、完了率 |
| 複数の値が混ざる、既出値を再質問する | 一項目ずつの entity collection と session 再利用 | 次の missing value だけを聞き、既出候補は利用前に確認する | 低精度候補を既成事実として使わない。turn 数増加が副作用 | field 混同率、重複質問率、収集 turn 数 |
| 綴られた ID・email・数字を誤って正規化する | spelled-character / spoken-number normalization と ambiguity recovery | field 型が分かり、明瞭な separator と文字だけを正規化する。複数解釈なら digit-by-digit clarification | 推測、部分値、未確認値で tool を呼ばない。通常文中の数値へ広げない | entity 完全一致率、曖昧値の確認率、誤 tool 引数率 |
| hard rule が無関係な場面にも発火する、類似 entity を取りこぼす | literal instruction trap の除去 | `always` 等を真の invariant に限定し、trigger・action・exception と対象 category を明示する | 必須の安全制約を弱めない。広すぎる category は過剰確認を招く | 適用対象の recall、反例での誤発火率、不要確認率 |
| accent が drift・誇張する、または一貫しない | accent fidelity を language policy と分離 | target accent、stability、pacing、stress、prosody、誇張防止のうち観測症状に関係する軸だけ指定する | language switching だけの症状には不採用。標準 voice で必要な fidelity が出ない場合は prompt を重ねず、Custom Voices または voice design へ分離する | accent 安定率、明瞭度、意図しない言語切替率 |
| 長い session や大量 context で古い情報を優先する、現在 state を失う | Long Context Behavior と source priority | Current State、Authoritative Sources、Historical / Background Sources を分け、currentness、authority、retrieved time、stale 情報の競合規則を明示する | 128k context だけを理由に採用しない。保存期間、retrieval、state 更新は実装層と分ける。新しいが非 authoritative な値を盲信しない | current authoritative source の採用率、stale source 誤使用率、state 正解率、token 使用量 |

## 組み合わせの判断

- sample phrase は tone や brevity の anchor になるが、反復を増やす場合は Variety と組み合わせる。
- alphanumeric readback は常時規則ではなく、該当する conversation state に限定できる。
- conversation flow と per-tool rule が同じ遷移を規定する場合は矛盾を除き、状態の exit condition と tool 成功条件を対応させる。
- Language Constraint と「利用者と同じ言語で応答」が競合する場合は、製品要件を確認するまでどちらも採用しない。
- Realtime 2 の `wait_for_user` は非指向性 audio、clarification は assistant 宛ての不明瞭発話に使い、同じ条件へ重ねない。1.5 または model 不明では no-op tool を要評価にする。
- reasoning effort と Reasoning rule は別介入として比較し、どちらが作用したか分からない変更を避ける。

## 不採用を明記する例

- 症状のない Reference Pronunciations section を skeleton 完成のためだけに追加する。
- 発話内容が長い問題に playback `speed` の変更だけを提案する。
- VAD event の誤りを unclear-audio 文言だけで解決済みと扱う。
- Realtime 2 以外へ `wait_for_user` を根拠なく転用する、または tool を用意せず無言処理を実装済みと扱う。
- Realtime 1.5 へ Realtime 2 固有の reasoning や既定 preamble を転用する。
- unavailable tool を prompt に詳しく記述して呼び出せるようにしようとする。
- escalation tool がない状態で handoff 文言だけを追加し、handoff 完了と扱う。
- 一つの A/B 比較で tone、flow、tool rules を同時に変更する。
