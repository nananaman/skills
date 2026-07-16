---
name: draft-issue
description: 実装前の仮説付き issue draft を作成する。repo の docs/agents/issue-tracker.md に従い、目的・背景・期待結果・やらないこと・調査メモを含む draft を作る。polished issue や実装 diff は作らない。PRD / Design Doc 作成、issue polish、実装、レビューだけの依頼では使わない。
---

# Draft Issue

実装に入る前の issue draft を作る。
この skill の成果物は「仮説付き draft」であり、実装設計契約ではない。
実装可能な状態まで磨く作業は `polish-issue` の責務である。

## Prerequisites

1. repo-local 設定を読む。

   ```text
   docs/agents/engineering-flow.md
   docs/agents/issue-tracker.md
   docs/agents/domain.md
   ```

2. 設定が存在しない場合は、作成へ進まず `setup-engineering-flow` の実行を提案する。
3. PRD / Design Doc が指定されている場合は読む。
4. 新機能・仕様変更なのに polished PRD がない場合は、issue 作成へ進まず `draft-prd` / `polish-prd` を提案する。
5. Design Doc が必要な変更なのに未作成・未完了なら、issue 作成へ進まずその理由を報告する。

## Issue draft の責務

draft issue は polished issue と同じ日本語見出し構造を使う。

- 埋められる項目は仮説として書く。
- 未調査・未確定の項目は削らず、`<!-- TODO(polish): ... -->` コメントを残す。
- `polish-issue` は TODO コメントを調査・検証で埋め、不要になった TODO を削除する。
- `assets/issue-template.md` を issue template として使う。

draft issue には入れすぎない。

- 正式な実装 diff を作らない
- 実装設計契約まで磨かない
- 未検証の仮説を事実として書かない
- Design Doc の主要判断を issue 側で勝手に変更しない

## Safety

- この skill では `git commit`、`git push`、APM pin 更新、skill install を実行しない。
- この skill の起動を、設定済み tracker への draft issue 作成の承認として扱い、作成前の確認は求めない。
- 既存 issue / file の上書き、欠損した採番情報の復旧、draft 作成を超える永続変更が必要な場合だけ停止して確認する。
- local markdown では、issue file と `SEQUENCE` を確認済みの tracker 文書として扱う。
- issue file 作成と `SEQUENCE` 更新後は報告で停止する。commit / push が必要なら別タスクとして確認する。

## Workflow

### 1. Classify entry point

入力がどれかを判定する。

- PRD / Design Doc から issue を切る
- ユーザーの説明から新規 issue を作る
- 既存 issue tracker に draft を追加する

新規 issue の対象が新機能・仕様変更なら polished PRD を要求する。小バグ、小リファクタ、trivial docs/config、主に技術改善の Design Doc 起点作業は例外としてよい。

情報が足りなければ一度に一つだけ質問する。

### 2. Read context

必要最小限の context を読む。

- repo-local flow docs
- referenced PRD / Design Doc
- existing related issues
- relevant code only when needed to avoid a clearly wrong draft

この段階で大きな調査や検証はしない。それは `polish-issue` の責務である。

### 3. Determine destination

`docs/agents/issue-tracker.md` に従う。

#### GitHub Issue

- issue title と body を作り、`gh issue create` を直ちに実行する。

#### Local markdown

- issue directory と `SEQUENCE` を読む。
- `SEQUENCE` は最後に使った番号として扱う。
- 次番号を決める。
- issue file を直ちに作成し、`SEQUENCE` を更新する。

`SEQUENCE` が存在しない場合は復旧方法を提案し、勝手に推測で作成しない。

#### Other

- 設定 prose に従う。
- 設定済みの draft 作成操作は直ちに実行する。既存 artifact の変更や draft 作成を超える不可逆な操作は確認する。

### 4. Write draft

`assets/issue-template.md` を seed として使う。

- local markdown の場合は template 全体を使い、`状態: Draft` にする。
- GitHub Issue の場合は `# {{title}}` を issue title として扱い、body からは H1 を省いてよい。
- 未確定欄には `<!-- TODO(polish): 何を確認すれば埋まるか -->` を残す。
- draft 時点で存在しない情報を推測で埋めない。

issue には `状態: Draft` または tracker 相当の状態を明記する。見出しは原則日本語にする。

### 5. Closeout

報告には次を含める。

- 作成した issue location / URL
- issue が draft であること
- 参照した PRD / Design Doc
- 残っている open questions
- 次に実行すべき skill: `polish-issue`
