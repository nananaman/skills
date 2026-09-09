---
name: ast-grep-practice
description: コーディングガイドの具体的な規則を、既存検査では不十分な場合にproject-localな構造lintへ落とす。ast-grepのrule・分類テスト・rewriteの作成や、kind・rule例の調査にも使う。通常の規範レビューや既存linter設定だけで足りる依頼には使わない。
---

# ast-grep の実践

ast-grep を「project-local な構造 lint / rewrite」として扱う。
自然言語プロンプトで注意喚起するより、再現可能な静的ルールに落とせるものを `sgconfig.yml` / `rules/` / `rule-tests/` に固定する。

## 基本方針

- 既存 linter / formatter / type checker や単純な文字列検査で十分なら、そちらを使い、ast-grepへ二重実装しない。
- ast-grep は「構造パターン」「project 固有の禁止 API」「安全な機械 rewrite」「既存 linter で表現しにくい文脈条件」に使う。
- rule 本体は原則として対象 repository に置く。global rule catalog は作らない。
- dotfiles の global `ast-grep` は開発者用 CLI として扱う。CI / repo scripts は対象 repository の既存 toolchain に合わせる。
- `fix` は意味保存が明らかな場合だけ付ける。少しでも文脈依存なら detection-only にして `note` に移行手順を書く。

## 標準レイアウト

対象 repository に ast-grep 基盤がない場合は、依頼範囲を確認する。
導入を依頼済みなら最小構成を project-local に作る。調査・提案だけの依頼なら導入案を提示する。

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

## 手順

1. ルール化する対象を確認する。
   - ガイドや合意を根拠に意図、禁止したいコード、似ているが許可したいコード、対象言語・パス、例外を明確にする。
   - 規範のうち構造で判定できる範囲を選ぶ。import aliasや同名の別オブジェクトなど、名前一致だけでは識別できないケースを確認し、型解決・実行時状態・意味判断まで保証しない。
   - 既存検査で十分なら、依頼範囲に応じてその設定を提案・変更して終える。意味判断のみなら検査の限界を説明し、ガイドやレビューで扱う。以降はast-grepを採用する場合に進む。
2. 既存基盤を調べる。
   - `sgconfig.yml` / `sgconfig.yaml`、`rules/`、`rule-tests/`、CI、package manager、task runner、dev shell などを確認する。
   - 既存の配置・コマンド・命名に合わせる。
3. テストを先に書く。
   - `rule-tests/<rule-id>-test.yml` に `valid` / `invalid` を置く。
   - 似て非なる valid case を必ず入れて false positive を防ぐ。
4. rule を書く。
   - `rules/<rule-id>.yml` に `id`、`language`、`severity`、`rule`、`message` を置く。
   - 対象範囲が限定されるなら `files` / `ignores` を明示する。
   - 必要なら `note` に背景と手動修正手順を書く。ガイドがある場合はそこからruleを参照し、message / noteからガイドの理由を辿れるようにする。ガイドは意図・適用範囲・例外、ruleは詳細な検査条件を持ち、条件一覧を二重管理しない。矛盾があれば合意に照らして揃える。
5. 検証する。
   - 分類テスト: `ast-grep test --skip-snapshot-tests`
   - scan: `ast-grep scan` または `ast-grep scan --error`
   - `files` / `ignores` による適用範囲は、対象パスと除外パスにfixtureを置いてscanでも確かめる。snippetの分類テストだけではパスの制限を検証できない。
   - 失敗したら rule と test のどちらが間違っているかを切り分ける。
6. snapshot は人間レビュー用に扱う。
   - 初回または rule 挙動を固定したい場合だけ `ast-grep test -U` を提案する。
   - snapshot diff は人間が確認してから commit する。
7. CI / scripts への組み込みは別判断にする。
   - 既存 CI があれば、その toolchain に合わせる。CI の新設は依頼範囲に含まれる場合に行う。
   - 導入・CI 組込を依頼済みなら、その実現に必要なローカル依存、lockfile、CI 設定の変更を作成・検証する。依頼範囲外の導入や外部システムの権限変更は確認する。

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

## ガイドからの直接依頼・振り返りからの引き渡し

規範を検査にする直接依頼は、このskillだけで進められる。
`retrospective-codify` から受け取る場合は、意図・具体例・適用範囲・既存検査の調査結果と、採用済みの変更範囲を再利用し、不足だけを調べる。

意味や設計の判断が必要な部分はガイドとレビューへ残す。たとえば時刻取得の直接呼び出しを検出しても、テストの時刻非依存全体を保証したことにはしない。

基盤がないrepoでも導入が採用済みなら、必要な最小設定とrule・テストを実装する。提案のみなら具体案を示し、配備しない。CI組み込みや既存違反の一括修正は依頼範囲で判断する。
規範から検査への対応例が必要なら [ガイドの規則を構造lintにする例](references/examples.md#ガイドの規則を構造lintにする) を読む。

## 完了条件

別の検査手段やレビューへ振り分けた場合は、選んだ理由と依頼範囲での結果を報告する。以下はast-grepを採用した場合に確認する。

- 既存 linter ではなく ast-grep を使う理由が説明されている。
- draft だけで止める場合は、`rules/*.yml` と `rule-tests/*-test.yml` の案、未実行の検証コマンド、次に確認すべき点を報告している。
- 実装まで行う場合は、`rules/*.yml` と `rule-tests/*-test.yml` が対応する `id` を持つ。
- valid / invalid に false positive / false negative を防ぐ例がある。
- 実装まで行う場合は、`ast-grep test --skip-snapshot-tests` と必要な `scan` の結果を報告している。
- `fix` を付けた場合、安全性の理由を説明している。
- CI 追加と lockfile 更新は依頼された導入範囲に収まり、commit / push はそれぞれ許可された場合だけ行っている。
