# Manifest Contract

snapshotの全hunkを変更意図ごとにまとめ、次のJSONとして保存する。

```json
{
  "version": 1,
  "title": "人間が差分全体を識別できる短いタイトル",
  "glossary": [
    {
      "id": "manifest",
      "term": "manifest",
      "definition": "変更groupと図の定義を保持するexplain-diff用JSON。"
    }
  ],
  "groups": [
    {
      "id": "stable-dash-case-id",
      "title": "変更グループ名",
      "summary": "何が変わったかの短い要約",
      "intent": "なぜこの変更が必要か",
      "impact": "影響する利用者・契約・component",
      "kind": "feature | fix | refactor | test | docs | tooling など",
      "risk": "要注意 | 注意 | 低リスク",
      "risk_reason": "人間が先に読むべき度合いの根拠",
      "needs_improvement": false,
      "needs_improvement_reason": "",
      "hunk_ids": ["h0123456789ab"]
    }
  ],
  "diagrams": [
    {
      "id": "request-flow",
      "title": "request処理のflow",
      "description": "入口からapplication処理までの依存を示す。",
      "format": "mermaid",
      "diagram_kind": "flowchart",
      "source": "flowchart TB\n  route[\"Route\\nrequestを受け取る\"] -->|calls| service[\"Service\\napplication処理を実行する\"]",
      "node_links": [
        {"node_id": "service", "group_ids": ["behavior"], "hunk_ids": ["h0123456789ab"], "term_ids": ["manifest"]}
      ]
    }
  ]
}
```

## Grouping

- 全hunk IDをちょうど一度だけ使う。
- groupは一つ以上のhunkを持つ。
- 同じ目的へ従属する変更を、fileが違うという理由で分割しない。
- unrelatedな目的を、同じfileにあるという理由でまとめない。
- 一つのhunkに複数の無関係な目的が混在する場合、初版ではhunkを分割しない。該当groupを `needs_improvement: true` にする。

CLIは未割当、重複割当、snapshotにないID、空group、重複group IDを拒否する。

## Diagrams

`diagrams` は任意。
差分の構造、flow、状態遷移をhunk一覧より明瞭に説明できる場合だけMermaidで追加する。

- `format` は `mermaid`。
- `diagram_kind` は `flowchart`、`stateDiagram-v2`、`sequenceDiagram` のいずれか。
- nodeには実装名だけでなく、役割を一文で書く。
- edgeには `calls`、`reads`、`publishes` など関係の意味を書く。
- `node_links` は `flowchart` だけで使い、Mermaid node IDをgroup、hunk、用語へ対応付ける。
  `stateDiagram-v2` と `sequenceDiagram` では空配列にする。
- Mermaidの `click` directiveは使わない。
- 通常の依存関係はflowchart、状態遷移はstate diagram、時系列が本質の場合だけsequence diagramを使う。

Mermaid 11.16.0をreportへ同梱し、`securityLevel: strict`、HTML label無効で描画する。

## Glossary

`glossary` は任意。
repository固有の名称、新しく導入した概念、略語、一般語と意味が異なる内部用語を、この変更で何を指すかが分かる形で定義する。
`function` や `JSON` など対象読者が通常知っている用語は追加しない。
CLIは重複IDと、nodeから参照された未知の用語IDを拒否する。

## Explanation

`summary` はdiffから観測できる変更内容、`intent` は実装セッションが保持する目的、`impact` は人間が確認すべき影響範囲を書く。
コード品質findingや、`review-diff-code` の代わりとなる問題探索は書かない。

次の場合は `needs_improvement: true` とし、理由を必須にする。

- 解説とdiffの対応を明瞭に示せない。
- 変更理由を実装planや作業判断へ結び付けられない。
- 計画外の変更が混ざる。
- 一つのhunkに無関係な意図が混ざる。

`要改善` は画面上の警告であり、feedbackへ自動追加されるfindingではない。

## Risk

riskはバグの疑いやreview findingのseverityではなく、人間が読む順序を表す。

| 値 | 目安 |
| --- | --- |
| `要注意` | 公開契約、認証・認可、永続データ、外部連携、不可逆な変更、広い影響範囲 |
| `注意` | runtime behaviorや複数componentへ影響するが、境界とrollbackが明瞭 |
| `低リスク` | test、docs、局所的な機械変更など、影響が限定的 |

CLIは `要改善`、risk、影響file数、hunk数、group IDの順で決定的に表示順を作る。
