---
name: draft-prd
description: 新機能・仕様変更の一言アイデア、メモ、会話ログ、既存 issue から PRD draft を作る。問題・対象ユーザー・要求を確定し、複数のプロダクト案を比較できる形にする。技術設計、Design Doc 作成、issue 作成、PRD polish、実装、レビューだけの依頼では使わない。
---

# Draft PRD

新機能・仕様変更のアイデアを、PRD template に沿った draft にする。
成果物は、問題・対象ユーザー・要求と複数案を確定し、案の選択を polish に渡せる draft である。

## Prerequisites

1. repo-local 設定があれば読む。

   ```text
   docs/agents/engineering-flow.md
   docs/agents/domain.md
   ```

2. 設定が存在しない場合でも、ユーザーが明示的に PRD draft 作成を求めていれば進めてよい。保存先は `docs/prd/` を使う。
3. 既存 issue / memo / conversation log が指定されていれば読む。

## PRD draft の責務

PRD は価値・範囲・成功条件の判断文書である。
`assets/prd-template.md` を記述内容と出力構造の source of truth とする。
template の `TODO(draft)` は draft 作成時に処理する。
`TODO(draft)` は仮置きではなく、調査・確認して確定する draft gate である。
技術設計・実装方針・issue 分割には踏み込まない。

## Safety

- この skill では `git commit`、`git push`、APM pin 更新、skill install を実行しない。
- この skill の起動を PRD draft file 作成の承認として扱い、書き込み前の確認は求めない。
- 既存 file の上書き、保存先の競合、draft 作成を超える永続変更が必要な場合だけ停止して確認する。
- PRD 作成後は報告で停止する。polish は `polish-prd` に委譲する。

## Workflow

### 1. Classify input

入力がどれかを判定する。

- 一言アイデア
- ユーザーのメモ / 会話ログ
- 既存 issue
- 既存 PRD draft の作り直し

情報が足りなければ一度に一つだけ質問する。

### 2. Confirm PRD is appropriate

PRD は新機能・仕様変更に使う。

次の場合は PRD ではなく Design Doc または issue から始める提案をする。

- CI 改善、build 改善、architecture 改善など、主に技術設計の問題である。
- 小バグ、小リファクタ、chore である。
- 実装作業単位が既に明確で、価値・範囲の判断が不要である。

ユーザーが PRD を明示的に求める場合は、理由を確認して続行してよい。

### 3. Read minimal context

必要最小限の context を読む。

- 指定された memo / issue / conversation log
- 関連する既存 PRD
- repo-local domain docs

`TODO(draft)` の確定に必要な context は調査する。
案の採否と採用案の具体化は行わない。

### 4. Draft PRD

`assets/prd-template.md` を seed として使う。

- `状態: Draft` にする。
- 複数のプロダクト案を `検討した案` に書き、同じ軸で Pros / Cons を比較できるようにする。
- 各 `TODO(draft)` を調査・確認して本文に置き換える。
- `TODO(draft)` を解消できない場合は polish へ送らず、draft を blocked として不足情報を報告する。
- template に最初からある `TODO(polish)` は polish 段階の作業として残す。
- 完成した draft に `TODO(draft)` を残さない。

### 5. Write draft

repo-local 設定に従って filename と保存先を決め、draft を直ちに書く。
設定がなければ `docs/prd/` を必要に応じて作り、title から作った短い kebab-case filename で保存する。
対象 file が既に存在する場合は上書きせず、既存 file を更新するか別名で作るかを確認する。

### 6. Closeout

報告には次を含める。

- 作成した PRD location
- draft であること
- 主要な TODO(polish)
- 次に実行すべき skill: `polish-prd`
- commit / push / APM pin 更新 / install は未実行であること
