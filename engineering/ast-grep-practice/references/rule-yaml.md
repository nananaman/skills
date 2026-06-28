# ast-grep rule YAML notes

rule YAML を書くときの最小リファレンス。
詳細は公式 docs と `ast-grep run --debug-query=ast` で確認する。

## 基本構造

```yaml
id: no-direct-env-access
language: TypeScript
severity: warning
rule:
  pattern: process.env.$KEY
message: process.env を直接参照しない。
note: |
  project の config wrapper を通す。
files:
  - "src/**/*.ts"
ignores:
  - "src/config/**"
```

よく使う field:

| field | 用途 |
| --- | --- |
| `id` | rule identifier。test file の `id` と一致させる。 |
| `language` | 対象言語。 |
| `severity` | `hint` / `warning` / `error`。 |
| `rule` | match 条件。 |
| `message` | 一行の検出理由。 |
| `note` | 背景、手動移行手順、fix を付けない理由。 |
| `fix` | 安全な自動修正。迷ったら付けない。 |
| `files` / `ignores` | 対象 path の限定。test との相性を確認してから付ける。 |

## rule operator

| operator | 意味 |
| --- | --- |
| `pattern` | code pattern に match。まずこれを試す。 |
| `kind` | AST node kind に match。 |
| `regex` | node text に正規表現 match。 |
| `all` | すべての条件に match。 |
| `any` | いずれかの条件に match。 |
| `not` | 条件に match しない。 |
| `has` | 子孫 node に条件がある。 |
| `inside` | 祖先 node に条件がある。 |
| `precedes` / `follows` | 隣接・近接する兄弟 node 条件。 |

`rule` 直下に複数 operator を並べると AND 条件になる。

```yaml
rule:
  pattern: fetch($$$ARGS)
  inside:
    kind: function_declaration
    stopBy: end
```

## metavariable

- `$X`: 単一 node。
- `$$$ARGS`: 0 個以上の node。空 match する。
- `$_`: capture しない wildcard。同じ名前でも同一性を要求しない。

metavariable は node 全体を占める必要がある。
`obj.on$EVENT` や文字列中の `$NAME` のような部分一致には使えない。

## constraints

metavariable の中身を絞る。
外側の構造条件は `has` / `inside` / `not` を使う。

```yaml
rule:
  pattern: $OBJ.$METHOD($$$ARGS)
constraints:
  METHOD:
    regex: '^(get|set|delete)$'
  OBJ:
    kind: identifier
```

## fix

```yaml
rule:
  pattern: oldClient.fetch($URL, $OPTS)
fix: newClient.request($URL, $OPTS)
```

`fix` は意味保存が明らかな場合だけ付ける。
以下は detection-only にする。

- 型推論、評価順、副作用、例外タイミングが変わる可能性がある。
- 呼び出し元や framework 文脈で正しい修正が変わる。
- 削除対象が式の一部で、周辺式と絡む。

削除 fix:

```yaml
fix: ''
```

行末の `;` や `,` まで消す必要がある場合は `expandEnd` を検討する。
ただし formatter が後段で走るなら、空行だけ残して formatter に任せる方が安全なこともある。

## test file

```yaml
id: no-direct-env-access
valid:
  - getEnv('NODE_ENV')
invalid:
  - process.env.NODE_ENV
```

- test file の `id` は rule file の `id` と一致させる。
- `valid` には false positive を防ぐ似て非なる例を入れる。
- `invalid` には最小例と実コードに近い例を入れる。
