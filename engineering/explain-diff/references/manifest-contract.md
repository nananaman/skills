# Manifest Contract

snapshot の全 hunk を、変更を理解するための因果順に並べた group へまとめ、次の JSON として保存する。

```json
{
  "version": 2,
  "title": "人間が変更全体を識別できる短いタイトル",
  "context": "変更前は何ができない、または何が問題だったか",
  "outcome": "変更後に利用者や system から観測できる到達状態",
  "glossary": [
    {
      "id": "manifest",
      "term": "manifest",
      "definition": "変更の物語と diff の対応を保持する explain-diff 用 JSON。"
    }
  ],
  "groups": [
    {
      "id": "stable-dash-case-id",
      "title": "この段階が果たす役割",
      "before": "この group が変更する直前の状態",
      "after": "この group により新たに成立する状態",
      "why": "目的に対して、なぜこの形を選んだか",
      "review_focus": "説明と diff の対応を確かめるために見る点",
      "hunk_ids": ["h0123456789ab"]
    }
  ],
  "diagrams": []
}
```

## Change story

説明は file 一覧や実装要素の分類ではなく、読み手が次の問いへ順番に答えられる物語にする。

1. `context`: なぜ変更が必要だったか。
2. `outcome`: 変更全体により何が可能になるか。
3. `groups`: その到達状態を、どの段階がどの順序で成立させるか。
4. `hunk_ids`: 各説明を裏付ける diff はどれか。

group の配列順はそのまま表示順になる。
公開 contract → 実装 → 検証のような固定順ではなく、その変更を最短で理解できる因果順を選ぶ。
リスクや file 数による自動並べ替えは行わない。

## Group explanation

- `title` は file 名や作業種別ではなく、到達状態への役割を書く。
- `before` と `after` は対比できる同じ粒度で書く。新規追加なら `before` に「存在しなかった」だけでなく、何が不可能だったかを書く。
- `why` は作業指示の言い換えではなく、目的に対してこの実装形を選んだ理由を書く。
- `review_focus` は品質 finding を作らず、説明が実装に対応しているかを確認する観点を書く。
- 実装名だけでは伝わらない場合は、利用者や system から観測できる表現を先に置き、実装名を根拠として添える。

実装意図がない、変更理由を対応付けられない、または一つの hunk に無関係な目的が混ざる場合は、推測で埋めず report 生成を停止する。

## Grouping

- 全 hunk ID をちょうど一度だけ使う。
- group は一つ以上の hunk を持つ。
- 同じ目的へ従属する変更を、file が違うという理由で分割しない。
- unrelated な目的を、同じ file にあるという理由でまとめない。
- 一つの hunk に複数の無関係な目的が混在し、明瞭な説明単位を作れない場合は report を生成しない。

CLI は未割当、重複割当、snapshot にない ID、空 group、重複 group ID を拒否する。

## Diagrams

`diagrams` は任意。
変更後の architecture、component 境界、処理 flow、data flow、状態遷移を文章より短く正確に示せる場合だけ Mermaid で追加する。

- `format` は `mermaid`。
- `diagram_kind` は `flowchart`、`stateDiagram-v2`、`sequenceDiagram` のいずれか。
- node には実装名だけでなく役割を書く。
- edge には `calls`、`reads`、`publishes` など関係の意味を書く。
- `node_links` は `flowchart` だけで使い、Mermaid node ID を group、hunk、用語へ対応付ける。
- `stateDiagram-v2` と `sequenceDiagram` では `node_links` を空配列にする。
- Mermaid の `click` directive は使わない。

実装順や group の因果順、import や file の一覧を図に置き換えただけなら省略する。
Mermaid 11.16.0 を report へ同梱し、`securityLevel: strict`、HTML label 無効で描画する。

変更対象 file 一覧は diagram とは別に、snapshot から report が常に生成する。
manifest へ file 一覧を重複して記述しない。

## Glossary

`glossary` は任意。
repository 固有の名称、新しく導入した概念、略語、一般語と意味が異なる内部用語を、この変更で何を指すかが分かる形で定義する。
対象読者が通常知っている一般的な用語は追加しない。
CLI は重複 ID と、node から参照された未知の用語 ID を拒否する。
