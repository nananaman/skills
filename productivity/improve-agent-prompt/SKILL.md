---
name: improve-agent-prompt
description: system prompt、agent instructions、tool description、AGENTS.md、skill 本文の agent-facing contract、prompt stack を、既存意図を保った最小差分で診断・改善する。重複、矛盾、過剰な手順指定、曖昧な成功条件・tool routing・自律性境界・停止条件を直すとき、または明示された対象モデルへ prompt を適応するときに使う。単なる文章校正・翻訳、skill の新規作成・構造・routing・lifecycle review、prompt 以外を含む API / model migration、実行型の empirical evaluation、静的 lint 化だけの依頼では使わない。
---

agent-facing prompt を、観測可能な outcome と判断可能な contract を持つ小さい指示へ改善する。
working prompt を全面 rewrite せず、保存すべき意図を固定してから measured failure または contract gap を最小差分で直す。

## Branch Router

最初に branch を 1 つ選ぶ。

| Branch | Trigger | Completion |
| --- | --- | --- |
| Diagnose | review、分析、問題点の指摘だけを求められた | preservation set、contract map、根拠付き finding、未検証事項を報告した |
| Improve | 書き換え、改善案、実際の編集を求められた | preservation set を維持した revised prompt または diff と検証結果を返した |
| Migrate | 対象モデルへの prompt 適応を明示された | 汎用変更とモデル固有変更を分け、同条件での評価計画または結果を返した |

依頼が diagnose / plan / review だけなら prompt を変更しない。
prompt 以外の API surface、model ID、runtime、tool implementation の変更が必要なら、その範囲を blocker または別 task として分ける。
skill の新規作成、構造、description / routing、review lifecycle は `skill-workbench` を入口にし、この skill は agent-facing prompt contract の診断・改善だけを担当する。

## Common Workflow

1. 対象と authority を固定する。
   - 対象 prompt、利用箇所、対象モデル、観測された failure、期待成果物を確認する。
   - 明示値がない項目は、既存ファイル、trace、eval、schema から安全に確認できる範囲を調べる。
   - authoritative な対象 prompt または必要な evidence を安全な lookup 後も取得できない場合、再構成や推測をせず、最小の不足 artifact を求めて止まる。
   - 外部 write、destructive action、costly run、scope expansion は、依頼で許可されていなければ実行しない。
   - completion: 対象、作業 layer、許可された変更範囲が一意になった。

2. preservation set を作る。
   - user-visible outcome、明示された値、safety / permission / business constraint、必要な evidence、tool routing、output shape、validation、stop rule を抽出する。
   - 相互に矛盾する項目は勝手に片方を削らず、優先順位を根拠から解決するか blocker にする。
   - completion: 削除・統合してはいけない既存契約を列挙した。

3. prompt contract を診断する。
   - [`references/contract-review.md`](./references/contract-review.md) を読む。
   - outcome、success criteria、constraints、evidence / prerequisites、authority boundary、tools、output、stop / fallback rules を必要な範囲で確認する。
   - 欠落、重複、矛盾、過剰指定、曖昧さを分け、各 finding を観測可能な failure または contract gap に結び付ける。
   - completion: finding ごとに evidence、影響、最小修正方向がある。

4. branch を実行する。
   - Diagnose: prompt を変更せず、contract map と finding を返す。
   - Improve: pruning、contradiction resolution、contract completion の順で、1 failure theme の最小差分を作る。
   - Migrate: Common Workflow 後に Model Migration を実行する。

5. 検証して終了する。
   - preservation set が維持されたことと、変更対象の failure / gap が解消されたことを確認する。
   - static check しか行っていない場合、性能改善を実証済みと表現しない。
   - 実行型評価が必要なら `empirical-prompt-tuning` へ渡すための scenario、assertion、baseline を提示する。
   - completion: validation result、未検証事項、次に必要な最小 action を報告した。

## Model Migration

1. 明示された対象モデルを維持する。
2. 対応する bundled reference があれば読む。GPT-5.6 family は [`references/model-gpt-5.6.md`](./references/model-gpt-5.6.md) を読む。
3. reference がない、または current / latest を求められた場合は、対象 provider の一次資料を確認する。
4. model、reasoning setting、prompt、tool set、runtime のうち 1 iteration で変える変数を 1 つにする。
5. 同じ representative cases と assertions で baseline と変更後を比較する。
6. 汎用 contract 修正とモデル固有 tuning を分けて報告する。

対応 reference がなく一次資料も確認できない場合、汎用 contract 改善だけを行い、モデル固有最適化は未検証と明記する。

## Change Rules

- outcome を書き、判断可能な path は agent に選ばせる。
- `always`、`never`、`must`、`only` は invariant に限定し、judgment call は decision rule にする。
- 同じ rule、approval boundary、style instruction を一箇所に統合する。
- required content を先に固定し、短文化では repetition、generic reassurance、optional background から削る。
- explicit user value を default や keyword map で上書きしない。
- 空の section を template に合わせて機械的に追加しない。
- 変更が複数 theme にまたがる場合は分割し、各差分が直す failure を明示する。

## Output

```md
## Diagnosis
- Target and layer:
- Preservation set:
- Contract gaps:
- Redundancy / contradictions:
- Residual uncertainty:

## Proposed changes
| Change | Type | Failure or gap addressed | Preservation risk |
| --- | --- | --- | --- |

## Revised prompt
<全文、diff、または Diagnose branch では省略>

## Validation
- Checks performed:
- Result:
- Not verified:
- Next smallest action:
```
