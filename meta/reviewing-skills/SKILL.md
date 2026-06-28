---
name: reviewing-skills
description: agent skill の品質をレビューする共通 rubric。metadata discoverability、positive / negative trigger、description / 本文整合、progressive disclosure、deterministic resources、pruning、failure modes、safety を確認するときに使う。
---

agent skill を、予測可能に動く小さな部品としてレビューするための共通 rubric。
差分レビューは `review-diff-skill`、全体棚卸しは `review-skill` を使い、この skill の観点を適用する。

## Core Principle

skill の目的は、確率的に振る舞う agent から予測可能なプロセスを引き出すこと。
予測可能性とは、毎回同じ出力を出すことではなく、毎回同じ種類の手順・判断・探索を行うことを指す。

## Review Axes

1. metadata / discoverability
   - `name:` が skill ディレクトリ名と一致しているか。
   - `name:` が小文字、数字、単一ハイフンのみで、1〜64 文字に収まっているか。
   - description が 1,024 文字以内で、skill 読み込み前の routing 情報として十分具体的か。
   - description に positive trigger と negative trigger が両方あり、近接領域の誤発火を避けられるか。
   - description が人間向け紹介文ではなく、agent が「読む / 読まない」を判断できる capability 文になっているか。

2. description / body consistency
   - description は紹介文ではなく起動条件になっているか。
   - description の各 trigger branch が本文の workflow に対応しているか。
   - 本文にある重要手順へ description から到達できるか。
   - 起動すべきでない場面まで拾う過発火がないか。

3. predictability
   - agent が毎回同じ種類の判断順序をたどれるか。
   - 手順が「考える」「よくする」などの曖昧語だけで終わっていないか。
   - 判断の分岐条件が本文にあるか。

4. progressive disclosure / information hierarchy
   - すぐ必要な手順が `SKILL.md` にあるか。
   - `SKILL.md` が通常 500 行未満で、routing 後すぐ読むべき情報に絞られているか。
   - 詳細、例、用語、長い評価表だけが references / GLOSSARY に逃がされているか。
   - template、schema、静的素材は assets に逃がされ、必要時に読む指示があるか。
   - references / assets / scripts が不必要に深い階層になっていないか。
   - 重要な停止条件が外部参照に埋もれていないか。
   - 通常 path で不要なファイルを最初から読ませる context bloat がないか。

5. deterministic resources / scripts
   - 壊れやすい解析、複雑な regex、繰り返し boilerplate を毎回 LLM に再生成させていないか。
   - scripts がある場合、tiny CLI として引数、stdout、stderr、exit status が agent に分かる形になっているか。
   - scripts が長期保守すべき library code を skill 内に抱え込んでいないか。
   - assets の template / schema を使うべき出力で、本文の prose だけに頼っていないか。

6. completion criteria
   - 各 step に完了判定があるか。
   - どの状態になったら次へ進むか、止まるかが明確か。
   - レビューや確認を要求する場合、finding が残ったときの扱いが明確か。

7. pruning
   - no-op: 書いても agent の挙動を変えない文がないか。
   - execution relevance: 本文中の各情報が agent の判断・手順・停止条件・出力形式のいずれかに効いているか。効かない情報は、削除するか、PR body / commit message / review note / README など skill 外へ分離できるか。
   - duplication: 同じ意味が複数箇所に散っていないか。
   - sediment: 古い前提や廃止済み名前が残っていないか。
   - sprawl: 全て有用でも長すぎて実行順を曖昧にしていないか。
   - human-doc drift: README、CHANGELOG、INSTALLATION guide など、人間向け文書が skill の実行契約と二重管理になっていないか。

8. failure modes
   - 曖昧な要求、権限不足、外部 tool 不在、対象不明のときに止まれるか。
   - ユーザーに聞くべきことと、自分で調べるべきことが分かれているか。
   - 途中でレビュー不能になったとき、不能理由を報告できるか。

9. safety
   - `git commit`、push、APM pin 更新、install、destructive command を勝手に実行しないか。
   - ユーザーの明示依頼が必要な操作が明示されているか。
   - 「完了条件」が配布や永続化の自動実行を誘発しないか。

## Review Levels

レビューは必要な強度を選ぶ。ただし強い review が必要な場面で弱い level だけで済ませない。

### Level 0: Static consistency

`SKILL.md` と関連ファイルを読み、metadata / discoverability と description / body consistency を確認する。
これはすべての skill review で必須。

- `name:` と配置ディレクトリが一致しているか。
- description が routing 情報として具体的で、positive / negative trigger を持つか。
- description の各 trigger branch が本文の workflow に対応しているか。
- 本文にある重要手順へ description から到達できるか。
- scope gap があれば、scenario より先に description か本文の修正を提案する。

### Level 1: Scenario walkthrough

median scenario 1 件と edge scenario 1〜2 件を作り、本文上で試走する。
これは `review-skill` と、commit / push / pin / install 前の重要な `review-diff-skill` で使う。

- 各 scenario に 3〜7 個の requirements checklist を置く。
- 少なくとも 1 つを `[critical]` にする。
- agent が description から起動すべき prompt と、起動すべきでない近接 prompt を確認する。
- 起動後、本文の workflow をどの順でたどるかを確認する。
- 追加 context を読むタイミングが Just-in-Time か、最初から不要ファイルを読ませていないかを確認する。
- 迷う分岐、本文にない discretionary fill-in、早すぎる完了、勝手な commit / push / pin / install へ進む導線を記録する。

### Level 2: Independent executor trial

別 agent / 別 session / reviewer に scenario を渡して実際に読ませる。
この level は skill 専用の empirical review protocol であり、author の自己読みに閉じないために使う。
subagent / reviewer を使えない環境では、自己再読で代替しない。実行不能理由を報告し、Level 2 実行済みとは言わない。

次の場合は Level 2 を要求する。

- 新規 skill。
- model-invoked skill の description を変えた。
- 高頻度利用 skill。
- 過去に誤作動した skill。
- skill の責務や workflow を大きく変えた。
- commit / push / APM pin 更新 / install 前の重要変更。

#### Independent reviewer contract

reviewer / subagent には、skill の作者意図ではなく固定した scenario と requirements を渡す。
requirements は依頼前に固定し、結果を見てから変更しない。

```md
You are an independent executor reading <target skill name> with a blank slate.

## Target skill
<path または全文>

## Scenario
<median or edge scenario>

## Requirements checklist
1. [critical] <必須項目>
2. <通常項目>
...

## Task
1. Read the target skill.
2. Execute the scenario mentally as an agent following that skill.
3. Produce the report below. Do not rewrite the skill.

## Report
- Deliverable: <実行するなら何を出すか、または実行 summary>
- Requirement achievement: 各項目の ○ / × / partial と理由
- Trace:
  - Understanding: instruction を読んで mental model を作れたか
  - Planning: approach / ordering を決められたか
  - Execution: 手順を実行できたか
  - Formatting: 期待される形に出力できたか
- Unclear points structured:
  - Issue: <観測された詰まり>
  - Cause: <instruction 側の原因>
  - General Fix Rule: <同種の失敗を防ぐ一般ルール>
- Discretionary fill-ins: skill 本文にない判断を補った箇所
- Retries: 同じ判断をやり直した回数と理由
```

#### Evaluation axes

| Axis | Capture | Rule |
| --- | --- | --- |
| Success / failure | requirements achievement | `[critical]` が 1 つでも × または partial なら failure |
| Accuracy | ○ = 1、partial = 0.5、× = 0 の達成率 | 全 requirements の平均 |
| Weak phase | Trace | Understanding / Planning / Execution / Formatting のどこで詰まったか |
| Unclear points | reviewer report | instruction 側の曖昧さとして扱う |
| Discretionary fill-ins | reviewer report | 本文にない判断の補完として扱う |
| Retries | reviewer report | 同じ判断のやり直し回数 |
| Steps / duration | tool usage が取れる場合だけ記録 | 補助指標。品質判断の主軸にしない |

#### Interpretation rules

- `[critical]` requirement を落とした場合は、どの item が落ちたか finding に明記する。
- Trace の弱い phase に合わせて修正位置を決める。Understanding の問題を Execution の細部で直さない。
- `General Fix Rule` はその場限りの文言ではなく、同種の skill に再利用できる抽象度で扱う。
- reviewer の finding はそのまま採用しない。対象本文で根拠を確認できるものだけ accepted にする。
- independent reviewer / subagent を使えない場合は、その理由を報告し、Level 2 を実行済みとは言わない。
- Level 2 の結果は reviewer の感想ではなく、固定済み requirements checklist に対する達成度として解釈する。

## Iteration Rules

Level 2 を実行して skill を直す場合は、反復単位を固定する。

- 1 iteration では 1 theme だけ直す。関連する 2〜3 個の微修正は同じ theme としてよい。
- 修正前に「この修正が requirements checklist / 判定文言のどの項目を満たすか」を明示する。axis 名だけから推測した修正は外れやすい。
- 新しい run では同じ reviewer / subagent を再利用しない。前回の改善を学習しているため。
- 通常の Level 2 反復は、2 回連続で新規 unclear points が 0 になるまで続ける。
- 高重要度 skill は、3 回連続で新規 unclear points が 0 になるまで続ける。
- 高重要度 skill の収束判定では、accuracy 改善が +3pt 以下、steps 変動が ±10% 以内、duration 変動が ±15% 以内であることを補助条件にする。
- 収束直前には、これまで使っていない hold-out scenario を 1 件追加する。直近平均より accuracy が 15pt 以上落ちる場合は overfitting とみなし、scenario 設計を見直す。
- 3 回以上 unclear points が減らない場合は、局所修正をやめて skill の構造分割や workflow 再設計を提案する。

### Fix propagation checks

修正効果は線形に出ない。反復時は次を確認する。

- Conservative: 複数軸を狙った修正が 1 軸にしか効かない。次回は判定文言単位へ絞る。
- Overshoot: command、config、expected output の組み合わせなど、1 つの構造情報が複数軸を同時に満たす。過剰分割しない。
- Zero-shoot: axis 名から推測した修正が requirements checklist の判定文言に届いていない。修正前に judgment link を明示する。

## Failure Pattern Ledger

同じ失敗を再発見しないため、Level 2 を伴う review では失敗パターン台帳を持つ。
永続ファイルに書く必要がある場合はユーザーに確認する。確認がない場合は session 内で管理する。

```md
- Pattern: <短く記述的な名前>
  - Example: <代表的な Issue>
  - General Fix Rule: <同種の失敗を防ぐルール>
  - Seen in: <iteration / scenario>
```

- 新しい finding の `General Fix Rule` が既存 pattern と一致する場合は、まず「なぜ既存修正で防げなかったか」を調べる。
- 同じ pattern が 3 回以上出る場合は、文言パッチではなく構造問題として扱う。

## Variant Exploration

収束しないが unclear points が減りにくい場合だけ、plateau 脱出として 2 variant を比較する。

- Conservative variant: 現行 skill に次の最小修正だけを加える。
- Exploratory variant: section 順序変更、密な段落の分割、重複削除、inline 最小例追加など、構造を 1 箇所だけ変える。

同じ scenario と固定済み requirements checklist で fresh reviewer / subagent に読ませ、accuracy、unclear points、weak phase、steps の順で比較する。
subagent に A/B の好みを直接聞かない。位置バイアスや自己選好が混ざるため、objective axis だけで比較する。

## Tool-use Interpretation

`tool_uses` や duration が取れる場合だけ補助指標として使う。
質的情報を主、量的情報を補助にする。

- scenario 間で `tool_uses` が 3〜5 倍以上違う場合、その skill は self-contained でなく references descent を強いている可能性がある。
- 全 scenario が 1〜3 steps なのに 1 scenario だけ 15+ steps になる場合、その scenario の recipe が `SKILL.md` 本体に不足している可能性が高い。
- 初期手順で references / assets / scripts を広く読む場合、progressive disclosure が崩れている可能性がある。
- accuracy が 100% でも、特定 scenario だけ steps が突出するなら構造欠陥として扱う。
- duration 短縮だけを目的にしない。必要な説明を削って脆くなることがある。

## Finding Rules

- high-confidence かつ action 可能な finding だけ報告する。
- 対象本文、description、README、APM 設定、scenario 結果などで根拠を確認する。
- `[critical]` requirement を落とす問題は、原則 high severity として扱う。
- speculative risk、cosmetic nit、好み、過剰な rewrite は rejected にする。
- finding は最小修正につながる形で書く。

## Output Shape

```md
## Evaluation

| Scenario | Success | Accuracy | Steps | Duration | Retries | Weak phase |
| --- | --- | --- | --- | --- | --- | --- |
| <name> | ○ / × | <percent> | <n or n/a> | <ms or n/a> | <n> | <phase or —> |

## Findings

### [severity] title
- Target: path:line
- Axis: metadata / description / predictability / hierarchy / deterministic resources / completion / pruning / failure modes / safety
- Problem: agent がどう誤作動するか、または何が保守しづらくなるか
- Evidence: 対象本文、関連ファイル、scenario 結果からの根拠
- Suggested fix: 最小修正
- Judgment link: この修正が満たす requirements checklist / 判定文言

## Structured reflection
- Issue: <観測された現象>
- Cause: <instruction 側の原因>
- General Fix Rule: <同種の失敗を防ぐ一般ルール>

## Ledger updates
- Added / Re-seen: <pattern>
```

finding がない場合は、どの review level まで実行したか、scenario 結果、actionable finding がないことを明示する。
