---
name: review-plan
description: 作成済みの一時実装planを、要求とrepository contextに照らして独立評価し、検討漏れ、誤った前提、検証不足、不要な複雑性のfinding ledgerと実装ready判定を返す。create-planの完了gate、実装着手前のplan review、別context reviewで使う。plan作成、対話によるgrilling、永続Design Docのpolish、実装済みdiff review、planの直接修正だけの依頼では使わない。
---

# Review Plan

作成済みの一時実装planが、追加の設計判断なしに実装でき、目的に対して必要以上に複雑でないかを独立評価する。
このskillはfindingを報告して終了し、planを変更しない。

## Review contract

- 対象は実装着手前のplanとする。要求、上流文書、関連code・test・設定を根拠に使う。
- lead agentはfresh reviewerを2人、可能なら並列に起動する。
- reviewerにはplan作成者のreasoning、自己評価、他reviewerのfindingを渡さない。
- Feasibility reviewerは[`assets/feasibility-reviewer.md`](./assets/feasibility-reviewer.md)を使い、目的達成、前提、変更境界、実装判断、検証の不足を評価する。
- Simplicity reviewerは[`assets/simplicity-reviewer.md`](./assets/simplicity-reviewer.md)を使い、既存機構で代替できる抽象化、将来要件の先取り、scope拡大、リスクに釣り合わない複雑性を評価する。
- reviewerはrepositoryを直接調査し、planの記述だけから一般論を生成しない。
- reviewerの出力はcandidate findingとする。lead agentがplan、要求、repositoryの事実で検証し、accepted / rejectedを決める。多数決では決めない。
- fresh reviewerを利用できない場合、同じcontextの自己reviewで代替せず`partial_failure`または`failed`として未評価範囲を残す。

## Finding judgment

Accepted:

- planのまま実装すると、目的未達、具体的な手戻り、contract break、検証不能、または不釣り合いな複雑性を生む。
- 要求、plan、上流文書、関連code・test・設定から根拠を確認できる。
- triggerまたは不足条件、影響、planに必要な最小変更を説明できる。

Rejected:

- repositoryを確認していない一般論、可能性の列挙、好みだけの別案。
- 実装時に安全に判断でき、planへ固定する必要がない局所的な手順。
- 要求にない将来拡張、broad rewrite、unrelated cleanup。
- 複雑性低減を主張しながら、目的や既存contractを満たさなくなる提案。

accepted findingは次のactionに分類する。

- `revise`: 既存の要求とrepository contextからplanを一意に直せる。
- `decision`: ユーザー判断または上流の設計判断が必要。
- `investigate`: 安全な追加調査やproofがなければ採否または修正内容を決められない。

severityは、未解決のまま実装を開始できない`blocker`と、残リスクとして明示すれば開始できる`advisory`だけを使う。

## Completion

次のいずれかで終了する。

- `ready`: 両reviewerが成功し、accepted `blocker`が0。
- `findings`: 両reviewerが成功し、accepted `blocker`が1件以上。
- `partial_failure`: 一方だけ成功した。`ready`とは表現しない。
- `failed`: plan、要求、repository、またはfresh reviewerを確保できず評価不能。

報告には次を含める。

- review targetと参照した要求・上流文書。
- reviewerごとのstatusと調査範囲。
- candidate ID、raised by、accepted / rejectedと理由。
- accepted findingのseverity、action、evidence、影響、最小plan変更。
- completion status、未評価範囲、実装ready判定。

`advisory`だけが残る場合は`ready`にできるが、残リスクを明示する。
plan修正後の再reviewは新しいreviewとして実行し、過去findingをreviewerへ渡さない。
