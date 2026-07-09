# Skill Design Principles

この reference は Create / Improve branch で draft または大きな構造変更を行う前に読む。
目的は、skill を予測可能に動く小さな部品として設計すること。

## Root Virtue: Predictability

skill の価値は、同じ出力を固定することではなく、agent が毎回同じ種類の process を取ることにある。
すべての設計判断は predictability に効くかで判定する。

## Invocation

- model-invoked: agent が自律発火すべき、または他 skill から到達させる必要がある場合だけ使う。description の context load を支払う。
- user-invoked: 人間が明示起動するだけでよい場合に使う。`disable-model-invocation: true` を付ける。ほかの skill から reach させる用途には使わない。

model-invoked description は、紹介文ではなく routing 情報である。
本文の workflow 要約を書くと、agent が本文を読まずに description だけで実行する shortcut を作る。

## Branches

branch は、同じ skill 内で異なる path を取る作業単位である。
branch ごとに次を固定する。

- trigger: その branch を選ぶ条件。
- steps: agent が実行する順序。
- completion criterion: どの状態なら branch が終わったと言えるか。
- output: ユーザーに返す形。

branch の完了条件が混ざるなら、SKILL.md ではなく reference へ逃がすか、別 skill に分ける。

## Information Hierarchy

1. In-skill step: 通常 path で必ず必要な手順。`SKILL.md` に置く。
2. In-skill reference: 通常 path で頻繁に必要な規則・定義。短ければ `SKILL.md` に置く。
3. Bundled reference: 一部 branch だけが読む詳細。`references/` に置き、読む条件を書く。
4. Assets / scripts: schema、template、deterministic CLI。必要時だけ使わせる。

判断基準:
- 全 branch が必要なら上に置く。
- 一部 branch だけが必要なら reference に逃がす。
- 毎回 LLM に再生成させると壊れる処理は script にする。

## Completion Criteria

各 step は checkable な完了条件で終える。
悪い例: 「十分にレビューする」「よい skill にする」。
良い例: 「positive / negative trigger が本文 branch に対応し、近接 skill の過発火候補が 1 件以上確認済み、または該当なしと報告済み」。

完了条件が曖昧だと premature completion が起きる。

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
| Premature completion | 完了条件が曖昧で早く終わる | step ごとの completion criterion を sharpen する |
| Duplication | 同じ rule / rubric / workflow が複数箇所にある | single source of truth に寄せる |
| Sediment | 古い前提、廃止名、使わない branch が残る | no-op / relevance check で削る |
| Sprawl | 有用な情報が多すぎて通常 path が重い | branch 化し、reference へ progressive disclosure する |
| No-op | 書いても agent の挙動が変わらない文 | 削除するか、強い completion criterion に変える |
| Negation | 禁止対象を強調して逆に想起させる | 原則は positive target を書き、必要な guardrail だけ禁止する |

## Pruning Test

各文ごとに確認する。

1. この文は agent の判断・手順・停止条件・出力形式を変えるか。
2. 同じ意味が別の場所にないか。
3. いまの branch で必要か。
4. README、PR body、commit message、review note に置くべき人間向け情報ではないか。

1 つでも失敗する文は、削除または下位 reference へ移す。
