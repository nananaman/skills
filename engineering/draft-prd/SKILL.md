---
name: draft-prd
description: 新機能・仕様変更の一言アイデア、メモ、会話ログ、既存 issue から PRD draft を作る。価値・範囲・成功条件を判断するための仮説と TODO(polish) を置く。技術設計、Design Doc 作成、issue 作成、PRD polish、実装、レビューだけの依頼では使わない。
---

# Draft PRD

新機能・仕様変更のアイデアを、PRD template に沿った draft にする。
成果物は完成 PRD ではなく、仮説と `TODO(polish)` を含む draft である。

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
draft-prd は以下を行う。

- 入力から PRD の仮説を抽出する。
- 不明な項目を勝手に埋めず、`<!-- TODO(polish): ... -->` を残す。
- 要求に関する曖昧さを見える化する。
- 技術設計・実装方針・issue 分割に踏み込まない。

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

この段階で大きな調査や設計検討はしない。

### 4. Draft PRD

`assets/prd-template.md` を seed として使う。

- 見出しは日本語にする。
- `状態: Draft` にする。
- 分かっていることは仮説として書く。
- 未確定欄には `<!-- TODO(polish): 何を確認すれば埋まるか -->` を残す。
- 受け入れ条件は observable になるよう試みるが、無理に確定しない。
- 成功条件は判断可能になるよう試みるが、無理に KPI を捏造しない。

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
