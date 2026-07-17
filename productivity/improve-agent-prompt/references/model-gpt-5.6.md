# GPT-5.6 Prompt Adaptation

明示的に GPT-5.6 Sol または GPT-5.6 family へ prompt を適応するときだけ読む。
API details、limits、pricing、availability はこの reference で扱わず、current official model guide を確認する。

Source: https://developers.openai.com/api/docs/guides/prompt-guidance-gpt-5p6

## Migration Baseline

1. working prompt と tool set を出発点にする。
2. model を切り替え、現在の reasoning effort を維持して representative eval を実行する。
3. obsolete scaffolding、重複 instruction、無関係な tool を一群ずつ削る。
4. measured regression を直す最小 instruction だけを追加する。
5. prompt または reasoning change ごとに同じ eval を再実行する。

model、reasoning effort、prompt、tool set、runtime を同時に変えない。
一度に全面 rewrite すると behavior change の原因を特定できない。

## GPT-5.6 Checks

- outcome、重要な constraints、available evidence、completion bar を明示し、実行 path は必要以上に固定しない。
- broad な brevity instruction が必要か再評価する。task 固有の必須内容と長さは prompt で指定し、API 利用時の既定詳細度は `text.verbosity` と分ける。
- personality と collaboration style は短く分け、goal、tool rule、stop condition の代用にしない。
- reasoning effort を上げる前に、success criterion、dependency、tool routing、verification loop の欠落を確認する。
- high / xhigh / max を global default にせず、representative eval の gain で判断する。

## Tool-heavy Prompts

- task-relevant tool だけを expose する。
- tool description には機能、利用条件、重要な return field、error behavior を書く。
- Programmatic Tool Calling は filtering、joining、sorting、deduplication、aggregation、batch、deterministic validation の bounded stage に限定する。
- PTC を使う場合は eligible tools、output schema、retry limit、stop condition、direct judgment への handoff を固定する。
- approval、semantic judgment、citation、final validation は direct tool call を優先する。

## Long-running State

- 最初の tool call 前に短い preamble を置き、更新は phase change または計画を変える finding に限定する。
- manual replay では assistant phase を保持する。
- compaction は major milestone 後に行い、compacted state を再解釈しない。
- persisted reasoning は objective、assumption、priority が安定している場合だけ再利用する。
- reusable prefix を安定させ、prompt caching の効果は workload で測る。

## Validation

- final response の正確性、完全性、required evidence を最優先で評価する。
- その後に tokens、latency、cost、calls、turns、retries を比較する。
- resource reduction は既存 eval を通過した場合だけ improvement と数える。
- regression は少数の real trace から failure mode と原因 instruction / contradiction を特定し、surgical edit 後に同じ case を再実行する。
