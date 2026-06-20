# skill evals

skill の効果を確認したいときに使う。

## いつ eval するか

- 出力の正誤を客観的に判定できる。
- 既存 skill の改善前後を比較したい。
- description の trigger 精度を確認したい。
- 失敗しやすい edge case がある。

文章品質や設計相談のような主観評価が中心の skill は、少数の代表 prompt を実行してユーザーに見てもらうだけでよいことが多い。

## 最小 eval

1. 実際に使いそうな prompt を 2〜3 個作る。
2. with-skill と baseline を比較する。
3. 成功条件を短く書く。
4. 結果を見て、skill 本文を直す。

## prompt の作り方

悪い prompt:

- 抽象的すぎる。
- 明らかに成功する。
- 現実の利用状況を含まない。

良い prompt:

- 実ファイル名、背景、制約がある。
- 迷いどころがある。
- skill がないと手順がぶれやすい。

## description eval

trigger description を調整するときは、should-trigger と should-not-trigger を混ぜる。

should-not-trigger は、完全に無関係な prompt ではなく、紛らわしい近傍ケースにする。
