---
name: reviewing-skills
description: agent skill の品質をレビューする共通 protocol。archetype fit、metadata discoverability、positive / negative trigger、description / 本文整合、progressive disclosure、deterministic resources、reference / diagnostic quality、smoke check、runtime smoke、failure modes、safety を確認するときに使う。
---

agent skill を、予測可能に動く小さな部品としてレビューするための共通 protocol。
差分レビューは `review-diff-skill`、全体棚卸しは `review-skill` を使い、この skill の観点と smoke check を適用する。

## Core Principle

skill の目的は、確率的に振る舞う agent から予測可能なプロセスを引き出すこと。
予測可能性とは、毎回同じ出力を出すことではなく、毎回同じ種類の手順・判断・探索を行うことを指す。

skill review は、作者の静的読解だけで終えない。
コードに対するテストと同じように、自然な入力から fresh agent がどの `SKILL.md` を読んでどう実行したかを smoke check で確認する。

## Review Axes

0. archetype fit
   - skill が workflow / reference / diagnostic / rubric / wrapper のどれを主目的にするか、本文から分かるか。
   - archetype に対して本文構造が合っているか。workflow は手順と停止条件、reference は利用者向け地図と実用断片、diagnostic は症状から確認・対処への分岐、rubric は評価軸、wrapper は委譲先と境界を中心にしているか。
   - 複数 archetype が混ざる場合、主責務と補助責務が明確で、別 skill に分けるべき責務過多になっていないか。

1. metadata / discoverability
   - `name:` が skill ディレクトリ名と一致しているか。
   - `name:` が小文字、数字、単一ハイフンのみで、1〜64 文字に収まっているか。
   - description が 1,024 文字以内で、skill 読み込み前の routing 情報として十分具体的か。
   - model-invoked skill では、description に positive trigger と negative trigger が両方あり、近接領域の誤発火を避けられるか。
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
   - workflow / rubric / wrapper skill では、`SKILL.md` が通常 500 行未満で、routing 後すぐ読むべき情報に絞られているか。
   - reference / diagnostic skill では、通常 path で必要な command map、頻出 recipe、制限、確認手順、troubleshooting が本文にあり、網羅資料や長い背景だけが外部参照に分離されているか。
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
   - destructive command やユーザー環境への永続変更を勝手に実行しないか。
   - ユーザーの明示依頼が必要な操作が明示されているか。
   - 「完了条件」が永続化操作の自動実行を誘発しないか。

10. reference / diagnostic quality
   - 対象 tool / product / API、利用者、対象外領域が冒頭と description で一致しているか。
   - バージョン、OS、architecture、provider、権限、課金、本番影響など、挙動が変わる前提が条件付きで書かれているか。
   - command / API / config の quick reference と詳細説明が矛盾していないか。
   - copy-paste 可能な例が安全で、destructive command や永続変更には確認条件・注意・dry-run 相当の確認手順があるか。
   - troubleshooting が「症状 → 確認 → 原因候補 → 対処 → まだ駄目な場合」の順でたどれるか。
   - 外部資料由来の内容では、upstream URL、取得日、license / attribution、更新時の確認方法が必要に応じて残っているか。
   - 古くなりやすい情報に `--help`、`version`、公式 docs などの再確認手段があるか。

## Review Protocol

レビューでは、対象に応じて次の checks を組み合わせる。
`review-diff-skill` と `review-skill` は、この protocol を対象 diff / 対象 skill に適用する adapter である。

### Static contract check

`SKILL.md` と関連ファイルを読み、metadata / discoverability と description / body consistency を確認する。
これはすべての skill review で必須。

- `name:` と配置ディレクトリが一致しているか。
- description が routing 情報として具体的か。
- model-invoked skill では positive / negative trigger を持つか。
- description の各 trigger branch が本文の workflow に対応しているか。
- 本文にある重要手順へ description から到達できるか。
- workflow、分岐条件、停止条件、出力形式が agent に判定可能か。
- skill archetype と本文構造が一致しているか。
- scope gap があれば、smoke check より先に description か本文の修正を提案する。

### Smoke check

fresh agent / subagent に自然な入力と必要最小限の状況を渡し、どの `SKILL.md` を読んでどう実行したかを観測する。
作者や同じ reviewer の mental walkthrough で代替しない。
subagent を使う場合は、harness が対応していれば background 実行し、verbose log で messages / tool calls / read files / commands / generated diff を確認する。
verbose log で対象 `SKILL.md` を read し、その後の output / tool use が本文に沿っていれば、その skill を使った evidence として扱う。
subagent / reviewer を使えない環境、または verbose log を確認できない環境では、実行不能理由や観測限界を報告し、確認できた範囲を明示する。

Smoke check は Execution smoke と Discovery smoke に分ける。
Execution smoke は、読まれた後に skill が正しく動くかを見る。
Discovery smoke は、model-invoked skill が自然な prompt から読まれるか / 読まれないかを見る。

#### Execution smoke

Execution smoke は、すべての対象 skill review で原則必須。
対象 `SKILL.md` を明示的に読ませ、自然な依頼と repo / task 状況に対して本文どおり実行できるかを確認する。

- user-invoked skill は、skill が選択済みという前提で Execution smoke を行う。
- model-invoked skill でも、Discovery smoke とは別に Execution smoke を行う。
- harness の明示起動仕様は skill review の責務外として扱う。
- checklist は skill 名や内部手順名ではなく、外部観測可能な期待結果で書く。
- 「この skill を使うこと」を期待値にしない。

#### Discovery smoke

Discovery smoke は、model-invoked skill の description / trigger を評価するときに実施する。
対象 skill 名や path を渡さず、harness が実際に discovery する環境で fresh subagent を起動し、verbose log で対象 `SKILL.md` が read されるかを見る。

- 最低限、positive case 1 件と negative case 1 件を用意する。
- positive case では、skill 名を含まない自然な user prompt と必要最小限の repo / task 状況を渡し、対象 `SKILL.md` が read されるかを見る。
- negative case では、近接するが対象外の user prompt で対象 `SKILL.md` が read されないかを見る。
- リスクが高い場合は、境界条件、競合 skill、過去の誤発火パターンを追加する。
- harness-real な discovery 環境を用意できない場合は、Discovery smoke を未検証として報告し、Execution smoke で代替したと言わない。

#### Smoke case design

各 case には次を固定する。

- Input: user prompt、repo 状況、diff summary、harness が実際に discovery する skill 配置など。
- Expected behavior: 外部から観測できる期待結果。skill 名や実装意図から逆算させない。
- Pass / fail criteria: どの出力・判断・停止条件なら pass か。

対象 skill の archetype に応じて次の case set を含める。

- workflow: median task で手順、停止条件、出力形式が守られる case。
- reference: 対象 tool / API の使い方を尋ねる positive usage case と、対象外の内部実装・ソース修正へ逸れない out-of-scope negative case。
- diagnostic: 典型症状から確認コマンド、原因候補、対処、escalation へ進む case。
- rubric: 評価対象に対して finding の採否と根拠を出す case。
- wrapper: 委譲先 skill / command の選択と、責務外で止まる case。

Execution smoke では、対象 skill が選択済みであることを前提として `SKILL.md` を読ませてよい。
Discovery smoke では、対象 skill 本文は最初から渡さない。
一時 repo / sandbox に skill を配置して検証する場合は、その環境から subagent を起動でき、harness が起動時にその skill を発見できることを確認する。
単に prompt で作業ディレクトリを `/tmp` へ指定するだけで harness が skill を再 discovery するとは限らない。

#### Smoke report

各 case について、Input / Expected / Actual / Result / Evidence / Finding link を残す。
Evidence は subagent の自己申告だけにせず、確認できる場合は verbose log の tool calls、read files、commands、command output、generated diff、final report に基づける。

```md
## Smoke check

| Case | Input | Expected | Actual | Result | Evidence | Finding link |
| --- | --- | --- | --- | --- | --- | --- |
| positive-basic | ... | ... | ... | pass/fail | ... | ... |
| negative-near | ... | ... | ... | pass/fail | ... | ... |

### Failure detail
- Case:
- Expected:
- Actual:
- Evidence:
- Likely instruction gap:
- Suggested fix:
```

### Runtime smoke check

skill の期待動作が runtime behavior に依存する場合は、fresh agent / subagent に一時環境で実コマンドを実行させる。
mental execution だけで済ませない。

Runtime smoke check が必要な例:

- 外部 CLI の実行。
- ファイル生成やファイル編集。
- Git 操作。
- sandbox / temp repo / local path dependency。
- install、build、test、lint、API call など外部環境に依存する挙動。

実施ルール:

- 一時 repo / sandbox を使い、global / user environment を明示許可なしに変更しない。
- unpublished skill は local path dependency や対象 repo の checkout を使って検証する。
- 実行した command、diff、生成ファイル、触った scope、install / runtime 結果、unclear points、requirements achievement を報告する。
- runtime smoke が必要だが実行できない場合は、理由と残リスクを明示する。

## Interpretation Rules

- smoke check の failure は、Expected と Actual の差分として扱う。
- subagent が「skill を使った」と自己申告しても、それだけを根拠にしない。verbose log の read files、tool calls、output shape など観測可能な evidence と照合する。
- finding は対象本文、description、関連ファイル、smoke 結果で根拠を確認できるものだけ accepted にする。
- speculative risk、cosmetic nit、好み、過剰な rewrite は rejected にする。
- failure の原因が harness、tool 制約、ユーザー環境にある場合は、skill 本文の finding と混同しない。
- Discovery smoke の negative case で対象 `SKILL.md` が read された場合は、description の過発火または negative trigger 不足として扱う。
- Execution smoke が pass しても、Discovery smoke の代替にはしない。
- user-invoked の明示起動形式は harness 側の責務であり、skill 本文の finding にしない。
- runtime smoke の failure は、手順・前提・停止条件・fallback のどこが不足しているかに分解する。

## Fix Iteration Rules

smoke check で skill を直す場合は、反復単位を固定する。

- 1 iteration では 1 theme だけ直す。関連する 2〜3 個の微修正は同じ theme としてよい。
- 修正前に「この修正が smoke case のどの Expected / Result を満たすか」を明示する。
- 新しい run では同じ reviewer / subagent を再利用しない。前回の改善を学習しているため。
- 2 回以上同じ pattern で失敗する場合は、文言パッチではなく skill の構造分割や workflow 再設計を検討する。

## Failure Pattern Ledger

同じ失敗を再発見しないため、smoke check を伴う review では失敗パターン台帳を持つ。
永続ファイルに書く必要がある場合はユーザーに確認する。確認がない場合は session 内で管理する。

```md
- Pattern: <短く記述的な名前>
  - Example: <代表的な failure>
  - General Fix Rule: <同種の失敗を防ぐルール>
  - Seen in: <case / iteration>
```

- 新しい finding の `General Fix Rule` が既存 pattern と一致する場合は、まず「なぜ既存修正で防げなかったか」を調べる。
- 同じ pattern が繰り返される場合は、局所修正ではなく構造問題として扱う。

## Tool-use Interpretation

`tool_uses` や duration が取れる場合だけ補助指標として使う。
質的情報を主、量的情報を補助にする。

- scenario 間で `tool_uses` が 3〜5 倍以上違う場合、その skill は self-contained でなく references descent を強いている可能性がある。
- 初期手順で references / assets / scripts を広く読む場合、progressive disclosure が崩れている可能性がある。
- smoke が pass でも、特定 case だけ steps が突出するなら構造欠陥として扱う。
- duration 短縮だけを目的にしない。必要な説明を削って脆くなることがある。

## Finding Rules

- high-confidence かつ action 可能な finding だけ報告する。
- 対象本文、description、関連 README、smoke 結果などで根拠を確認する。
- smoke case の critical な Expected を落とす問題は、原則 high severity として扱う。
- speculative risk、cosmetic nit、好み、過剰な rewrite は rejected にする。
- finding は最小修正につながる形で書く。
- reference / diagnostic skill の finding では、情報の欠落そのものではなく、その欠落が誤回答、危険な command 実行、条件差分の見落とし、troubleshooting の行き止まりをどう起こすかを示す。

## Output Shape

```md
## Evaluation
- Static contract check: 実施結果の要約
- Smoke check: 実施 case、pass/fail、fresh agent / subagent を使ったか
- Runtime smoke check: 実施した / 不要 / 実施不能と理由
- Archetype: 判定した archetype と、その構造が妥当か
- Accepted findings: 件数と要約
- Rejected findings: 件数と理由

## Smoke check

| Case | Input | Expected | Actual | Result | Evidence | Finding link |
| --- | --- | --- | --- | --- | --- | --- |
| <case> | <input> | <expected> | <actual> | pass/fail | <evidence: read files / tool calls / output> | <finding or —> |

## Findings

### [severity] title
- Target: path:line
- Axis: archetype fit / metadata / description / predictability / hierarchy / deterministic resources / completion / pruning / reference / diagnostic quality / failure modes / safety
- Problem: agent がどう誤作動するか、または何が保守しづらくなるか
- Evidence: 対象本文、関連ファイル、smoke 結果からの根拠
- Suggested fix: 最小修正
- Judgment link: この修正が満たす smoke case の Expected / Result

## Structured reflection
- Issue: <観測された現象>
- Cause: <instruction 側の原因>
- General Fix Rule: <同種の失敗を防ぐ一般ルール>

## Ledger updates
- Added / Re-seen: <pattern>
```

finding がない場合は、Static contract check と smoke check を実施したうえで actionable finding がないことを明示する。
