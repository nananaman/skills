---
name: draft-design-doc
description: 技術改善・設計変更、または PRD 後に必要な大きい変更について Design Doc draft を作る。問題・制約を確定し、複数の設計案を比較できる形にする。PRD 作成、Design Doc polish、issue 作成、実装、レビューだけの依頼では使わない。
---

# Draft Design Doc

Design Doc の draft を作る。
成果物は、問題・制約と複数案を確定し、案の選択を polish に渡せるたたき台である。

Design Doc は、技術・設計上の問題を解くための設計判断文書である。

入口は二つある。

- 技術・設計上の問題から直接始める場合
  - CI 改善、build 改善、architecture 改善、module 分割、migration strategy など
- PRD の要求を実現するために必要になる場合
  - API / DB / 状態設計 / 移行 / セキュリティ / 信頼性などの設計判断が必要な変更

新機能・仕様変更の要求そのものを決める文書ではない。
要求の価値・範囲・成功条件を決める必要がある場合は、先に PRD を作る。

## Prerequisites

1. repo-local 設定があれば読む。

   ```text
   docs/agents/engineering-flow.md
   docs/agents/domain.md
   ```

2. PRD の要求を実現するための Design Doc であれば、指定された PRD を読む。技術・設計上の問題から直接始める場合、PRD は不要である。
3. 関連 issue / docs / code が指定されていれば読む。

## Draft の責務

`assets/design-doc-template.md` を記述内容と出力構造の source of truth とする。
template の `TODO(draft)` は draft 作成時に処理する。
`TODO(draft)` は仮置きではなく、調査・確認して確定する draft gate である。
採用案は draft で決めない。

## Safety

- この skill では `git commit`、`git push`、APM pin 更新、skill install を実行しない。
- この skill の起動を Design Doc draft file 作成の承認として扱い、書き込み前の確認は求めない。
- 既存 file の上書き、保存先の競合、draft 作成を超える永続変更が必要な場合だけ停止して確認する。
- Design Doc 作成後は報告で停止する。polish は `polish-design-doc` に委譲する。

## Workflow

### 1. Classify input

入力がどれかを判定する。

- 技術改善・設計変更のアイデア
- PRD から派生した大きい変更
- 既存 issue から Design Doc が必要になったもの
- 既存 Design Doc draft の作り直し

情報が足りなければ一度に一つだけ質問する。

### 2. Confirm Design Doc is appropriate

Design Doc は次のような場合に使う。

- 技術・設計上の問題を解く必要がある。
- PRD の要求を実現するために、重要な設計判断が必要である。
- 複数 issue に分割される。
- API / DB / 状態設計 / 互換性 / 移行に影響する。
- CI / build / architecture / module boundary など技術設計の判断が主である。
- 失敗したときの手戻りが大きい。
- セキュリティ、プライバシー、信頼性、負荷・コストの判断が必要である。

新機能・仕様変更の「何を作るか」「なぜ作るか」「成功条件」を決める段階なら、Design Doc ではなく PRD から始める。
小バグや小リファクタで設計判断が不要なら、`draft-issue` を提案する。

### 3. Read minimal context

必要最小限の context を読む。

- 指定された PRD / issue / docs
- 関連する既存 Design Doc / ADR
- 検討案を出すために必要な周辺コード

`TODO(draft)` の確定と案の比較に必要な範囲は調査する。
採用案を前提にした詳細検証と設計確定は `polish-design-doc` の責務である。

### 4. Draft Design Doc

`assets/design-doc-template.md` を seed として使う。

- `状態: Draft` にする。
- `検討した案` に検討中の案を複数書く。
- 各案を同じ軸で Pros / Cons 比較できるようにする。
- 各 `TODO(draft)` を調査・確認して本文に置き換える。
- `TODO(draft)` を解消できない場合は polish へ送らず、draft を blocked として不足情報を報告する。
- template に最初からある `TODO(polish)` は、採用案を決めて設計へ昇格する polish 段階の作業として残す。
- 完成した draft に `TODO(draft)` を残さない。

### 5. Write draft

repo-local 設定に従って filename と保存先を決め、draft を直ちに書く。
設定がなければ `docs/design/` を必要に応じて作り、title から作った短い kebab-case filename で保存する。
対象 file が既に存在する場合は上書きせず、既存 file を更新するか別名で作るかを確認する。

### 6. Closeout

報告には次を含める。

- 作成した Design Doc location
- draft であること
- 検討中の案
- 主要な TODO(polish)
- 次に実行すべき skill: `polish-design-doc`
- commit / push / APM pin 更新 / install は未実行であること
