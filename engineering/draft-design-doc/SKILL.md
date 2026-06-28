---
name: draft-design-doc
description: 技術改善・設計変更、または PRD 後に必要な大きい変更について Design Doc draft を作る。複数の設計案を検討した案に並べ、仮説と TODO(polish) を置く。PRD 作成、Design Doc polish、issue 作成、実装、レビューだけの依頼では使わない。
---

# Draft Design Doc

Design Doc の draft を作る。
成果物は完成設計ではなく、複数の設計案・仮説・`TODO(polish)` を含むたたき台である。

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

- 目的を数行で端的に置く。
- 技術設計としてのやらないことを仮置きする。
- 背景・制約・用語を仮置きする。
- `検討した案` に検討中の設計案を複数書く。
- 各案には Pros / Cons / Conclusion の見出しを残すが、draft では TODO のままでよい。
- 未検証の前提は事実扱いせず、案の説明や TODO に一時的に残す。
- 採用案を無理に確定しない。

## Safety

- この skill では `git commit`、`git push`、APM pin 更新、skill install を実行しない。
- Design Doc file 作成などの永続化はユーザー確認後だけ行う。
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

大きな検証や設計確定はしない。それは `polish-design-doc` の責務である。

### 4. Draft Design Doc

`assets/design-doc-template.md` を seed として使う。

- 見出しは日本語にする。
- `状態: Draft` にする。
- `検討した案` に検討中の案を複数書く。
- draft の Pros / Cons / Conclusion は TODO のままでよい。
- 未検証事項がある場合は、案の説明に一時的に書いてよい。
- 概要 / 詳細設計は採用案が未決なら TODO のままでよい。
- Mermaid 図はどの章でも使ってよい。概要・詳細設計では特に推奨する。
- 状態を持つ設計では、概要または詳細設計に状態遷移図を書く TODO を残す。

### 5. Confirm before write

保存先、filename、body を提示し、ユーザー確認後だけ書く。
デフォルト保存先は repo-local 設定に従う。未設定なら `docs/design/` を提案する。

### 6. Closeout

報告には次を含める。

- 作成した Design Doc location
- draft であること
- 検討中の案
- 主要な TODO(polish)
- 次に実行すべき skill: `polish-design-doc`
- commit / push / APM pin 更新 / install は未実行であること
