# Skill Creator Glossary

## predictability

agent が毎回同じ種類のプロセスを取る度合い。同じ出力を出すことではない。

## model-invoked

`description` により agent が自律的に発見できる skill。context 負荷を払う代わりに、発見可能性を得る。

## user-invoked

`disable-model-invocation: true` により、ユーザーが明示的に呼ぶときだけ使う skill。context 負荷はないが、ユーザーの記憶負荷が増える。

## context 負荷

常時 context に載る情報が agent の注意と token を使うコスト。主に model-invoked skill の description が生む。

## 記憶負荷

ユーザーが「どの skill があり、いつ使うか」を覚えるコスト。user-invoked skill が増えるほど大きくなる。

## branch

skill が扱う distinct な起動ケース。description には branch を書き、同じ branch の言い換えを重ねない。

## information hierarchy

agent がすぐ必要とする順に情報を配置する考え方。steps、本文 reference、外部 reference の順に置く。

## completion criterion

step が完了したかを判断する条件。明確で検査可能なほど、早すぎる完了を防げる。

## progressive disclosure

一部の場面でだけ必要な情報を、`references/` や `GLOSSARY.md` に逃がし、必要なときだけ読ませる設計。

## no-op

書いても agent の挙動を変えない指示。

## duplication

同じ意味が複数箇所にある状態。

## sediment

古くなった説明や判断が堆積して残っている状態。

## sprawl

全て有用でも、skill が長すぎて読みづらくなっている状態。

## leading word

agent の事前知識を利用して、長い説明を短く安定した概念に圧縮する語。
