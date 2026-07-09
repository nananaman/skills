# Skill Evaluation Loop

この reference は Create / Improve branch で、skill の効果を baseline と比較して検証する必要がある場合だけ読む。
すべての skill 変更で必須ではない。

## When to Use

- routing が難しい model-invoked skill。
- 過去に品質問題が再発した skill。
- 客観評価できる成果物を生成する skill。
- ユーザーが empirical / eval / benchmark を求めた場合。

## Loop

1. 評価したい behavior を 2〜3 件選ぶ。
   - 実際のユーザーが言いそうな prompt にする。
   - positive case と negative / near-miss case を混ぜる。
   - skill 名や内部手順名を期待値にしない。

2. baseline を決める。
   - 新規 skill: skill なし。
   - 既存 skill 改善: 変更前 skill の snapshot。

3. with-skill と baseline を同じ iteration で走らせる。
   - subagent を使える場合は並列に走らせる。
   - 出力、tool use、read files、duration / tokens が取れるなら保存する。

4. assertion を作る。
   - 客観的に判定できる expected behavior だけ assertion にする。
   - 主観評価が必要な成果物は、人間 review を主にする。

5. grade / compare する。
   - assertion pass/fail、品質差、token / duration の tradeoff を見る。
   - baseline でも pass する assertion は非識別的として見直す。

6. 改善する。
   - feedback から一般化できる instruction gap だけを skill に反映する。
   - test prompt への overfit を避ける。
   - 同じ helper や script を複数 run が再生成したら、bundled script 化を検討する。

7. 再実行する。
   - 同じ case で regression を見た後、必要なら case を増やす。
   - meaningful progress がなくなったら止め、残リスクを報告する。

## Output

```md
## Evaluation Loop
- Target skill: <path>
- Iteration: <n>
- Baseline: no skill / old skill snapshot / other
- Cases: <n>
- Assertions: <n or qualitative only>

## Results
| Case | Baseline | With skill | Judgment | Evidence |
| --- | --- | --- | --- | --- |

## Changes Applied
- <instruction gap fixed>

## Residual Risk
- <unverified or subjective area>
```
