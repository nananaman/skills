# Skill Review Protocol

この reference は Review diff / Review whole branch で読む。
レビューは静的読解だけで終えず、可能な限り fresh agent / subagent の smoke check で実行時のズレを見る。

## Review Axes

1. metadata / discoverability
   - `name:` が directory 名と一致しているか。
   - `name:` が小文字、数字、単一ハイフンのみ、1〜64 文字か。
   - description が 1,024 文字以内で routing 情報として具体的か。
   - model-invoked skill では positive / negative trigger があるか。

2. description / body consistency
   - description の trigger branch が本文 workflow に対応しているか。
   - 本文にある重要手順へ description から到達できるか。
   - 起動すべきでない近接領域まで拾っていないか。

3. predictability
   - agent が毎回同じ種類の判断順序をたどれるか。
   - 分岐条件が本文にあるか。
   - 「考える」「よくする」だけで手順が終わっていないか。

4. progressive disclosure / information hierarchy
   - すぐ必要な手順が `SKILL.md` にあるか。
   - 詳細、例、用語、長い評価表だけが `references/` にあるか。
   - template / schema は `assets/`、壊れやすい処理は `scripts/` に逃がせているか。
   - 重要な停止条件が外部 reference に埋もれていないか。

5. deterministic resources / scripts
   - 繰り返し boilerplate や壊れやすい解析を毎回 LLM に再生成させていないか。
   - scripts が tiny CLI として引数、stdout、stderr、exit status を持つか。
   - 長期保守すべき library code を skill 内に抱えていないか。

6. completion criteria
   - 各 step に完了判定があるか。
   - finding が残ったときの扱いが明確か。
   - stop / ask / continue の条件が分かれているか。

7. pruning
   - no-op 文がないか。
   - 同じ意味が複数箇所にないか。
   - 古い前提や廃止名が残っていないか。
   - 人間向け文書と skill 実行契約が二重管理になっていないか。

8. failure modes
   - 対象不明、権限不足、外部 tool 不在、レビュー不能で止まれるか。
   - ユーザーに聞くことと、自分で調べることが分かれているか。

9. safety
   - destructive command や永続変更を勝手に実行しないか。
   - commit / push / pin / install が明示依頼 gated か。

## Static Contract Check

すべての review で必須。

- `SKILL.md` と関連ファイルを読む。
- `name:`、directory、description、本文 branch の対応を確認する。
- workflow、分岐条件、停止条件、出力形式が agent に判定可能か確認する。
- scope gap があれば、smoke check より先に description か本文の修正を提案する。

## Smoke Check

fresh agent / subagent に自然な入力と必要最小限の状況を渡し、どの `SKILL.md` を読んでどう実行したかを観測する。
作者や同じ reviewer の mental walkthrough で代替しない。

### Execution Smoke

すべての対象 skill review で原則必須。
対象 skill が選択済みであることを前提に、自然な依頼と repo / task 状況で本文どおり実行できるかを見る。

- checklist は skill 名や内部手順名ではなく、外部観測可能な期待結果で書く。
- 「この skill を使うこと」を期待値にしない。
- subagent を使えない場合は、理由と観測限界を報告し、実行済みとは言わない。

### Discovery Smoke

model-invoked skill の description / trigger を評価するときに実施する。
対象 skill 名や path を渡さず、harness が実際に discovery する環境で fresh subagent を起動し、対象 `SKILL.md` が読まれるかを見る。

- positive case 1 件以上、negative near-miss 1 件以上を用意する。
- Execution smoke が pass しても Discovery smoke の代替にはしない。
- harness-real な Discovery smoke を用意できない場合は未検証として報告する。

### Runtime Smoke

skill の期待動作が外部 CLI、ファイル生成、Git 操作、sandbox / temp repo、install、build、test、lint、API call に依存する場合に実行する。

- 一時 repo / sandbox を使い、global / user environment を明示許可なしに変更しない。
- 実行した command、diff、生成ファイル、触った scope、結果を報告する。
- 必要だが実行できない場合は、理由と残リスクを明示する。

## Smoke Case Shape

```md
- Case: <短い名前>
- Input: <user prompt / repo 状況 / diff summary>
- Expected: <外部から観測できる期待結果>
- Pass criteria: <どの出力・判断・停止条件なら pass か>
```

## Interpretation Rules

- smoke failure は Expected と Actual の差分として扱う。
- subagent の「skill を使った」という自己申告だけを根拠にしない。
- verbose log、read files、tool calls、commands、generated diff、final output を確認できる範囲で evidence にする。
- harness や tool 制約による failure を skill 本文の finding と混同しない。
- 2 回以上同じ pattern で失敗する場合は、文言パッチではなく構造分割や workflow 再設計を検討する。

## Finding Rules

- high-confidence かつ action 可能な finding だけ accepted にする。
- target、axis、problem、evidence、suggested fix、judgment link を持たせる。
- smoke case の critical expected を落とす問題は high severity として扱う。
- speculative risk、cosmetic nit、好み、過剰な rewrite は rejected にする。
