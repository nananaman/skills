# 良い skill を書くための基準

skill の目的は、確率的に振る舞う agent から予測可能なプロセスを引き出すこと。ここでの予測可能性とは、毎回同じ出力を出すことではなく、毎回同じ種類の手順・判断・探索を行うことを指す。

## 起動方式

### model-invoked

`description` を持つ skill。agent が自律的に発見でき、ユーザーも明示的に呼べる。他 skill からも到達しやすい。

代償として、description が常に context に載る。agent が自力で到達する必要がある場合だけ選ぶ。

### user-invoked

`disable-model-invocation: true` を持つ skill。ユーザーが明示的に呼ぶときだけ使う。

context 負荷はないが、ユーザーが存在を覚えておく必要がある。手動起動だけで十分な skill に向いている。

## description

model-invoked skill の description は紹介文ではなく起動条件である。

- 先頭に skill の中心概念を置く。
- 何をする skill かを書く。
- distinct branch だけを書く。
- 同じ branch の言い換えを重ねない。
- 本文に置ける説明を description に詰め込まない。

undertrigger を避けるために強く書いてよい。ただし、強いことと長いことは違う。目標は「強く短い description」。

## 情報階層

skill の内容は、agent がすぐ必要とする順に置く。

1. `SKILL.md` の steps: agent が実行する順序つき手順。
2. `SKILL.md` の reference: 実行中に参照する規則・定義・判断基準。
3. 外部 reference: `references/` や `GLOSSARY.md` に置く詳細資料。

全 branch が必要とするものは本文に置く。一部の branch だけが必要とするものは、明確な pointer を添えて外部 reference に逃がす。

## 完了条件

各 step には、完了したかどうかを agent が判断できる条件を置く。

弱い例:

- 変更リストを作る。
- いい感じに整理する。

強い例:

- 変更された各 model について、API・永続化・テストへの影響を列挙する。
- description の各 trigger branch が本文の手順に対応していることを確認する。

完了条件が曖昧だと、agent は次の手順に急ぎやすい。

## 分割の基準

skill を分ける理由は主に二つ。

- 起動方式で分ける: 独立して agent が発見すべき概念がある。
- 手順で分ける: 後続手順が見えているせいで、現在の手順を早く切り上げてしまう。

分けるたびに、model-invoked なら context 負荷、user-invoked なら記憶負荷が増える。分割は、その負荷を払う価値があるときだけ行う。

## pruning

skill は追加より削除が難しい。次を定期的に削る。

- duplication: 同じ意味が複数箇所にある。
- sediment: 古くなった説明が残っている。
- sprawl: 全て有用でも長すぎる。
- no-op: 書いても agent の挙動が変わらない。

各文について「この文は agent の挙動を変えるか」を確認する。変えないなら削る。

## leading word

強い一語で、長い説明を圧縮できることがある。

例:

- 「速く、決定的で、低コストな反復」より「tight loop」。
- 「かなり丁寧に質問する」より「relentless」。

leading word は agent の事前知識を利用する。独自用語を作るより、既に意味が強い語を選ぶ。
