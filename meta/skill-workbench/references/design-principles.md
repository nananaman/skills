# Skill Design Principles

この reference は Create / Improve branch で draft または大きな構造変更を行う前に読む。
目的は、skill を必要な context へ導く小さな interface として設計すること。

## Root Principle: Reliable Outcome, Minimal Constraint

skill が安定させるのは agent の探索順序ではなく、outcome、判断境界、必要な evidence、検証方法である。
詳細な rule は、domain 固有の gotcha、authority / safety boundary、誤終了を防ぐ gate のように、周辺 context と agent の判断だけでは回復できない場合に限る。

設計判断は次の順で行う。

1. 周辺 context と agent の判断で解けるなら書かない。
2. 必要な知識へ到達できればよいなら、短い routing と reference を置く。
3. 出力の形を安定させるなら、例を増やす前に schema、型、状態、rubric を設計する。
4. 決定的に検査・変換できるなら asset / script / test にする。
5. 重要な safety / authority rule だけは明示的な constraint として残す。

## Invocation

- model-invoked: agent が自律発火すべき、または他 skill から到達させる必要がある場合だけ使う。description の context load を支払う。
- user-invoked: 人間が明示起動するだけでよい場合に使う。`disable-model-invocation: true` を付ける。ほかの skill から reach させる用途には使わない。

model-invoked description は、紹介文ではなく routing 情報である。
本文の workflow 要約を書くと、agent が本文を読まずに description だけで実行する shortcut を作る。

## Interface Contract

skill は agent-facing prompt として、必要な範囲で次の contract を明示する。

- outcome: ユーザーに見える到達状態。
- completion: branch が終了したと判断できる状態。
- constraints: safety、permission、business rule、scope の境界。
- evidence / prerequisites: 判断や action の前に必要な根拠と確認。
- authority boundary: 自律実行できる action と確認が必要な action。
- output: 必須の内容、形式、検証結果。
- stop / fallback rules: retry、代替、質問、abstain、終了の条件。

すべてを prose の見出しとして追加しない。
型、schema、test、既存コード、template、rubric のほうが高い忠実度で表せる場合はそれを interface にする。
agent の判断を変えず、周辺 context から分かる項目は重ねて説明しない。

## Branches

branch は、異なる outcome または completion を持つ作業単位である。
branch ごとに最低限次を固定する。

- trigger: その branch を選ぶ条件。
- completion criterion: どの状態なら branch が終わったと言えるか。
- output: ユーザーに返す形。

steps は順序が correctness や safety に影響する場合だけ固定する。
完了条件が混ざる branch は reference へ逃がすのではなく、branch または skill を分ける。

## Information Hierarchy

1. In-skill interface: branch routing と全 branch に必要な invariant。`SKILL.md` に置く。
2. In-skill guide: 通常 path で必ず必要な判断や gate。短ければ `SKILL.md` に置く。
3. Bundled reference: 一部 branch だけが読む詳細。`references/` に置き、読む条件を書く。
4. Rich reference: test、code、mockup、rubric など、高忠実度な既存成果物を必要時に参照する。
5. Assets / scripts: schema、template、deterministic CLI。必要時だけ使わせる。

判断基準:
- 全 branch が必要なら上に置く。
- 一部 branch だけが必要なら reference に逃がす。
- 周辺 repo から分かることを skill に複製しない。
- 毎回 LLM に再生成させると壊れる処理は script にする。

## Completion Criteria

branch-level completion と、重要な safety / authority gate は観測可能にする。
中間の探索 step は、誤終了や不可逆な action を防ぐ場合だけ completion を固定する。

曖昧な「十分に確認する」ではなく、必要な evidence、検証結果、残った finding の扱いで終了状態を表す。
チェック項目を満たすこと自体を outcome にしない。

## Leading Words

leading word は、agent が作業中に掴める短い概念語である。
例: predictability、branch、completion criterion、single source of truth、sprawl、sediment。

使い方:
- 同じ意味を長文で何度も説明している箇所を、強い leading word に畳む。
- description、本文、README の用語を揃え、routing と実行時の思考を接続する。
- 弱い一般語（よく、丁寧に、適切に）ではなく、行動を変える語を使う。

## Failure Modes

| Failure | 症状 | 防御 |
| --- | --- | --- |
| Premature completion | 完了条件が曖昧で早く終わる | branch-level completion と重要 gate を観測可能にする |
| Duplication | 同じ rule / rubric / workflow が複数箇所にある | single source of truth に寄せる |
| Sediment | 古い前提、廃止名、使わない branch が残る | no-op / relevance check で削る |
| Sprawl | 有用な情報が多すぎて通常 path が重い | branch 化し、reference へ progressive disclosure する |
| No-op | 書いても agent の挙動が変わらない文 | 削除するか、強い completion criterion に変える |
| Negation | 禁止対象を強調して逆に想起させる | 原則は positive target を書き、必要な guardrail だけ禁止する |
| Contradiction | 同じ状況に複数の相反する rule が適用される | preservation set と interface contract を基準に優先順位または decision rule を固定する |
| Overconstraint | agent が checklist 消化に寄り、周辺 context を使えない | outcome と invariant を残し、探索手順と例を削る |
| Example anchoring | 例の形だけを再現し、問題に合う探索を狭める | schema、型、rubric、状態遷移で interface を表す |

## Pruning Test

各文ごとに確認する。

1. この文は agent の判断・手順・停止条件・出力形式を変えるか。
2. 同じ意味が別の場所にないか。
3. いまの branch で必要か。
4. 周辺 context、tool description、code、test、schema から既に分かることではないか。
5. README、PR body、commit message、review note に置くべき人間向け情報ではないか。

1 つでも失敗する文は、削除または下位 reference へ移す。
