# Prompt Contract Review

この reference は Diagnose / Improve の共通診断で読む。
各項目を prompt の見出しに変換するためではなく、agent の判断に必要な契約が存在するか検査するために使う。

## Contract Map

| Element | Question | Keep or add when |
| --- | --- | --- |
| Outcome | ユーザーに見える到達状態は何か | 手順はあるが完成状態が曖昧 |
| Success criteria | 終了前に何が真である必要があるか | premature completion が起きうる |
| Constraints | safety、permission、business、scope の境界は何か | 誤った action や範囲拡大を防ぐ |
| Evidence / prerequisites | 判断・action 前に必要な根拠は何か | lookup や validation を飛ばせる |
| Authority boundary | 自律実行と確認要求の境界はどこか | 過剰確認または無断 action が起きる |
| Tools | 何を、いつ、どの結果・error を見て使うか | route が文脈や前提に依存する |
| Context placement | 契約をどの layer へ置き、いつ取得するか | 常時 load、重複、低忠実度な prose を減らせる |
| Output | 必須の内容、形式、長さ、検証結果は何か | downstream consumer が期待する形がある |
| Stop / fallback | retry、代替、質問、abstain、終了はいつか | loop、guess、早期終了が起きる |

## Diagnostic Passes

### Preservation

- 明示された user value、artifact、length、structure、genre、factual claim を優先して残す。
- safety / permission gate、required evidence、output field、validation、failure handling を削除候補から外す。
- prompt stack では同じ rule の authoritative source を特定する。

### Pruning

削除または統合候補:

- 同じ rule の言い換え。
- 挙動を変えない style / process instruction。
- 挙動を変えない example。
- agent が安定して実行できる behavior の逐語的手順。
- task と無関係な tool または tool description。

残す対象:

- user-visible outcome。
- success criteria と stop condition。
- safety、permission、business、evidence constraint。
- 文脈依存の tool routing。
- required output と validation。

### Contradiction

- 同じ状況で `ask first` と `continue autonomously` が競合していないか。
- brevity instruction が required content を落とさないか。
- tool loop 最小化が evidence、calculation、citation、validation より優先されていないか。
- personality / style rule が factual accuracy や artifact preservation と競合していないか。
- prompt stack の上位・下位 layer に異なる default や禁止がないか。

矛盾は instruction を追加して覆い隠さない。
適用条件、優先順位、authority boundary のいずれかを一箇所で明示する。

### Autonomy and Approval

- answer、explain、review、diagnose、plan は read-only inspection と報告を既定にする。
- change、build、fix は依頼範囲の local change と non-destructive validation を許可する。
- external write、destructive action、purchase / costly run、material scope expansion は明示的な許可境界を置く。
- safe local action を明示したら、同じ approval rule を複数箇所で繰り返さない。
- 承認を求める前に、変更予定の artifact / file と action を列挙する。承認後に別 artifact、追加 action、materially different scope が必要と分かった場合は、その範囲へ進まず再承認を求める。

### Tools and Evidence

- prerequisite retrieval / discovery / validation を final action より前に置く。
- 独立 read は並列化できるが、前の結果で次が変わる call は逐次にする。
- empty、partial、suspiciously narrow な結果には 1〜2 個の meaningful fallback を定義する。
- absence of evidence を factual no に変換しない。
- citation が必要なら、support 対象、十分な evidence、欠落時の behavior を定義する。

### Context Placement

各 instruction は、内容だけでなく authoritative な配置先を確認する。

- product 全体の役割と invariant は system / agent instructions に置く。
- repository 固有で、code や filesystem から発見できない gotcha は AGENTS.md 系の context に置く。
- task や branch に依存する workflow と詳細は skill / reference へ分け、必要時だけ取得できる導線を残す。
- session をまたぐ事実や preference は、利用可能なら memory に置く。
- code、test、schema、型、rubric、mockup、linter のほうが高忠実度な契約は、prose で重複管理しない。
- task と無関係な turn でも常時 load する必要がない情報を、上位 prompt に置かない。
- 同じ rule が複数 layer にある場合は authoritative source を一つにし、必要なら他方は導線だけにする。

prompt 以外の変更が依頼範囲外なら実装せず、移動先と必要な別 task を finding として報告する。

### Tool Interface

- tool の能力と利用条件が、名前、引数、型、enum から判別できるか確認する。
- required / optional field、排他的な操作、状態遷移を prose の例だけに依存させない。
- return value が次の判断に必要な状態を返し、error と正常な空結果を区別できるか確認する。
- tool description は schema から分からない利用条件、重要な return field、failure behavior に絞る。
- prompt 内の example が interface の不足を補っているだけなら、interface 改善を優先して提案する。

### Examples and Rich References

example は、schema で表現できない semantic boundary、固有の taste、紛らわしい反例、観測済み failure を伝える場合に残す。
通常手順の再現、tool schema の言い換え、偶然選んだ一つの探索 path の固定にしかならない example は削除候補にする。

文章による説明より code、test、schema、型、rubric、mockup、canonical implementation のほうが正確な場合は、rich reference への置換を提案する。

### Output and Brevity

- 結論、required facts、decision、material caveat、next action を preservation priority にする。
- 短くするときは introduction、repetition、generic reassurance、optional background から削る。
- personality は tone を、collaboration style は質問、仮定、自律性、検証、不確実性の扱いを制御する。
- broad label ではなく、実際の writing choice を短く指定する。

### Terminal Outcomes

- 変更、提案、finding が 0 件でも正常終了できるようにする。
- reusable evidence なし、完全重複、ユーザーによる却下、必要情報の未取得、変更不要をそれぞれ終端状態として扱えるか確認する。
- 何も行わない場合は、理由と確認した範囲を報告し、成果物を作るためだけの提案を追加しない。
- 必要な入力がなければ最小の不足情報を一度求め、それでも取得できなければ未完了理由を報告して停止する。

### Validation Integrity

- 必須の test、review、render、external tool、fresh-agent check を実行できない場合、別の確認を同等の代替として扱わない。
- 未実施の検証、実行できない理由、残る risk、次に必要な確認を報告する。
- 必須検証が未実施、失敗、または actionable finding を残している場合、検証済み・完了済みと表現しない。
- optional validation と completion gate を区別し、optional check の不能だけで正常な作業を止めない。
- 実行型評価では working prompt を baseline にし、同じ representative cases と assertions で変更後と比較する。
- 一度に変える変数を一つにし、regression の原因を追跡できるようにする。
- token、latency、cost、tool call の削減は、既存の品質基準を満たした場合だけ improvement と数える。

## Change Test

各変更について確認する。

1. どの観測可能な failure または contract gap を直すか。
2. preservation set のどの項目に影響するか。
3. 削除または統合で解決できず、新規 instruction が必要か。
4. static check で判定できるか、representative eval が必要か。
5. ほかの failure theme と分離できているか。
6. 承認が必要な場合、許可される artifact / file / action が一意か。
7. 変更なしの終了と、必須検証不能時の終了を正しく表現できるか。
8. instruction の配置先と取得時点は適切か。
9. example や prose を interface または rich reference で置き換えられないか。

答えられない変更は適用しない。
