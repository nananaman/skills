---
name: ast-grep-practice
description: ast-grep を project-local な構造 lint / rewrite として導入・運用する。既存 linter で表現しにくい AST パターンの rule draft、rule-tests、sgconfig.yml、検証コマンドを作るとき、または kind 名・rule 例を調べるときに使う。単なる grep、既存 linter 設定で足りる規約、global rule catalog 作成、commit / push / APM pin / install だけの依頼では使わない。
---

# ast-grep Practice

ast-grep を「project-local な構造 lint / rewrite」として扱う。
自然言語プロンプトで注意喚起するより、再現可能な静的ルールに落とせるものを `sgconfig.yml` / `rules/` / `rule-tests/` に固定する。

## 基本方針

- 既存 linter / formatter / type checker で表現できるなら、そちらを優先する。
- ast-grep は「構造パターン」「project 固有の禁止 API」「安全な機械 rewrite」「既存 linter で表現しにくい文脈条件」に使う。
- rule 本体は原則として対象 repository に置く。global rule catalog は作らない。
- dotfiles の global `ast-grep` は開発者用 CLI として扱う。CI / repo scripts は対象 repository の既存 toolchain に合わせる。
- `fix` は意味保存が明らかな場合だけ付ける。少しでも文脈依存なら detection-only にして `note` に移行手順を書く。

## 標準レイアウト

対象 repository に ast-grep 基盤がない場合は、まず導入提案を出す。
ユーザーが承認したら、最小構成を project-local に作る。

```text
project/
  sgconfig.yml
  rules/
    <rule-id>.yml
  rule-tests/
    <rule-id>-test.yml
  rule-utils/        # 必要になったら追加
```

最小 `sgconfig.yml`:

```yaml
ruleDirs:
  - rules
testConfigs:
  - testDir: rule-tests
```

## Workflow

1. ルール化する対象を確認する。
   - 禁止したいコード、許可したいコード、対象言語、対象パスを明確にする。
   - 既存 linter で表現できるかを先に確認する。
   - 表現できるなら ast-grep rule ではなく既存 linter 設定を提案する。
2. 既存基盤を調べる。
   - `sgconfig.yml` / `sgconfig.yaml`、`rules/`、`rule-tests/`、CI、package manager、task runner、dev shell などを確認する。
   - 既存の配置・コマンド・命名に合わせる。
3. テストを先に書く。
   - `rule-tests/<rule-id>-test.yml` に `valid` / `invalid` を置く。
   - 似て非なる valid case を必ず入れて false positive を防ぐ。
4. rule を書く。
   - `rules/<rule-id>.yml` に `id`、`language`、`severity`、`rule`、`message` を置く。
   - 対象範囲が限定されるなら `files` / `ignores` を明示する。
   - 必要なら `note` に背景と手動修正手順を書く。
5. 検証する。
   - 分類テスト: `ast-grep test --skip-snapshot-tests`
   - scan: `ast-grep scan` または `ast-grep scan --error`
   - 失敗したら rule と test のどちらが間違っているかを切り分ける。
6. snapshot は人間レビュー用に扱う。
   - 初回または rule 挙動を固定したい場合だけ `ast-grep test -U` を提案する。
   - snapshot diff は人間が確認してから commit する。
7. CI / scripts への組み込みは別判断にする。
   - 既存 CI がある場合だけ、対象 repo の toolchain に合わせた最小追加を提案する。
   - CI 追加、package install、lockfile 更新はユーザー確認なしに実行しない。

## rule draft の最小形

```yaml
id: no-direct-debug-print
language: TypeScript
severity: warning
rule:
  pattern: console.log($$$ARGS)
message: debug print を残さない。
note: |
  production code では project の logger を使う。
  単純置換で意味が変わる可能性があるため detection-only にする。
```

テスト:

```yaml
id: no-direct-debug-print
valid:
  - logger.info('ok')
  - console.error('error path')
invalid:
  - console.log('debug')
  - console.log('a', 'b')
```

## `fix` を付ける判断

`fix` を付けてよい例:

- deprecated API の引数順・副作用・戻り値が同じで、置換先が一意。
- import path の機械置換など、project 全体で合意済みの移行。
- 削除しても意味が残らない一時 debug 文で、formatter が後段で走る。

`fix` を付けない例:

- 型推論や compile error が変わる。
- 引数評価順、short-circuit、副作用、例外タイミングが変わる。
- framework の文脈や呼び出し元によって正しい修正が変わる。
- 削除対象が式の一部で、周辺式と絡む。

迷ったら detection-only にし、`note` に手動移行の判断基準を書く。

## 参照資料

必要になった時点で読む。

- `references/rule-yaml.md`: rule YAML の構造、operator、metavariable、`fix` の注意点。
- `references/kind-catalog.md`: 代表的な kind 名と、未知の kind を調べる方法。
- `references/examples.md`: 実践的な rule / test 例。

kind 名が不明な場合:

```bash
ast-grep run --pattern '<code>' --lang <language> --debug-query=ast
ast-grep run --pattern '<code>' --lang <language> --debug-query=cst
```

## retrospective-codify から受け取る場合

`retrospective-codify` が「機械検出可能」と分類した知見を受け取ったら、次を確認する。

- 対象 repo に ast-grep 基盤があるか。
- 禁止・許可したい concrete code example があるか。
- 既存 linter で代替できない理由があるか。
- rule draft と test draft までで止めるのか、実装・検証まで行うのか。

基盤がない repo では、勝手に `sgconfig.yml` を作らず、導入案と最小 diff を提示して確認する。

## 完了条件

- 既存 linter ではなく ast-grep を使う理由が説明されている。
- draft だけで止める場合は、`rules/*.yml` と `rule-tests/*-test.yml` の案、未実行の検証コマンド、次に確認すべき点を報告している。
- 実装まで行う場合は、`rules/*.yml` と `rule-tests/*-test.yml` が対応する `id` を持つ。
- valid / invalid に false positive / false negative を防ぐ例がある。
- 実装まで行う場合は、`ast-grep test --skip-snapshot-tests` と必要な `scan` の結果を報告している。
- `fix` を付けた場合、安全性の理由を説明している。
- CI 追加、lockfile 更新、commit / push はユーザーの明示依頼なしに行っていない。

