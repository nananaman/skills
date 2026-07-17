---
name: polish-design-doc
description: Design Doc draft を、人間がこの設計で進めてよいか判断でき、issue 分割へ進める文書へ磨く。複数案を調査・比較し、採用案を概要/詳細設計へ昇格し、リスク評価と検討した案を完成させる。PRD 作成、issue 作成、通常実装、diff review だけの依頼では使わない。
---

# Polish Design Doc

Design Doc draft を「この設計で進めてよいか判断でき、次に issue 分割へ進める文書」に磨く。
複数案を調査・比較し、採用案を固定する。

## Contract

polished Design Doc は、次を満たす。

- 目的が数行で端的である。
- 技術設計としてのやらないことが明確である。
- 背景・制約が分かる。
- 用語が定義されている。
- 採用する設計の概要が分かる。
- 詳細設計が実装判断に十分である。
- 状態を持つ設計では、概要または詳細設計に状態遷移がある。
- Mermaid 図が必要な箇所にある。
- 落とし穴が設計上の既知の問題として書かれている。
- セキュリティ / プライバシー / 負荷・コスト / 信頼性 / 開発・運用への影響が評価されている。
- リスク評価系の章が「なし」だけで終わっていない。
- 採用案が概要・詳細設計へ昇格し、不採用案と理由が `検討した案` に残っている。
- `TODO(polish)` が残っていない。
- issue 分割に進める。

## 併用する skill

この Design Doc を対象に、`japanese-tech-writing` skill を併用して `grilling` session を実行する。

この skill は Design Doc の構造と完了条件を定める。
`grilling` は曖昧さを一問ずつ潰す手順を定める。
`japanese-tech-writing` は文章品質を定める。

## Safety

- この skill では `git commit`、`git push`、APM pin 更新、skill install を実行しない。
- この skill では issue / 実装 diff を作らない。
- 検証のために変更したコード・一時ファイルは、Design Doc 更新前に戻すか削除する。
- Design Doc 更新前に polished body をユーザーへ提示し、確認後だけ更新する。

## Workflow

### 1. Load context

対象 Design Doc draft を読む。
repo-local 設定があれば読む。

```text
docs/agents/engineering-flow.md
docs/agents/domain.md
```

Design Doc が存在しない場合は `draft-design-doc` を提案して止める。
`TODO(draft)` が残っている、または draft が blocked の場合は polish へ進まず、`draft-design-doc` で draft gate を解消するよう報告して止める。
PRD の要求を実現するための Design Doc であれば、PRD 参照を読む。技術・設計上の問題から直接始まった Design Doc では、PRD は不要である。

### 2. Grill one question at a time

一度に一つずつ問いを立てる。
コードベース、既存 docs、既存 ADR から答えられることは、ユーザーに聞く前に調べる。
draft に残った `TODO(polish)` と、polished gate を阻害する具体的な不足・矛盾を優先する。
draft で根拠とともに確定している設計判断は一律に問い直さない。

不足・矛盾がある場合に詰める問い:

- この設計で何が実現されるか。
- 技術設計として何をやらないか。
- 背景・制約は十分に説明されているか。
- 用語は揃っているか。
- 比較すべき案は揃っているか。
- 採用案はどれか、なぜか。
- 採用案の詳細設計は実装判断に十分か。
- 状態を持つなら状態遷移が明示されているか。
- 落とし穴として受け入れる既知の問題は何か。
- セキュリティ / プライバシー / 負荷・コスト / 信頼性 / 開発・運用への影響は評価されているか。
- issue 分割へ進めるか。

### 3. Investigate and verify

必要に応じてコード・テスト・docs・外部仕様を読む。
不確実性が高い場合は、小さな検証コード、typecheck、test、benchmark を実行してよい。

検証前に worktree snapshot を取る。

```bash
git status --short --untracked-files=all
```

検証で worktree を変更した場合は、最終確認として再度実行する。

```bash
git status --short --untracked-files=all
```

戻してよいのは、この skill が作った変更・一時ファイルだけである。開始前から存在したユーザー変更は戻さない。Design Doc 文書以外に、この skill が作った modified / staged / untracked が残っている場合は戻す。既存変更と区別できない場合は戻さず、polished にせず blocked として報告する。

### 4. Decide adopted design

`検討した案` にある候補を比較し、採用案を決める。

- 採用案は `概要` と `詳細設計` に反映する。
- 採用案の仕組み、成立条件、重要な Pros / Cons を `概要`・`採用理由`・`詳細設計`・`落とし穴` へ欠落なく反映してから、その subsection を `検討した案` から外す。
- `検討した案` には不採用案だけを残し、各案の `Conclusion` に不採用理由を書く。
- 採用案が決められない場合は polished にせず blocked として報告する。

### 5. Rewrite Design Doc

`../draft-design-doc/assets/design-doc-template.md` の構造に合わせて Design Doc を更新する。

- template の `TODO(draft)` は draft 作成用の指示であり、polished Design Doc に転記しない。
- polished gate を満たした Design Doc は `状態: Polished` に更新する。
- `TODO(polish)` コメントは polished Design Doc に残さない。
- リスク評価系の章は `なし` / `特になし` / `影響なし` だけで終わらせない。
- 考慮不要な場合も、なぜ不要かを書く。
- Mermaid 図はどの章でも使ってよい。概要・詳細設計では特に推奨する。
- 状態を持つ設計では、概要または詳細設計に Mermaid stateDiagram などで状態遷移を書く。

### 6. Validate polished gate

更新前に以下を自己確認する。

- 人間がこの設計で進めてよいか判断できるか。
- 目的が数行で端的か。
- 技術設計としてのやらないことが明確か。
- 採用案の概要と詳細設計が十分か。
- 落とし穴が既知の問題・限界として honest に書かれているか。
- セキュリティ / プライバシー / 負荷・コスト / 信頼性 / 開発・運用への影響が評価されているか。
- リスク評価系の章が「なし」だけで終わっていないか。
- 採用案が概要・詳細設計に反映され、`検討した案` に重複して残っていないか。
- 採用案の仕組み、成立条件、重要な Pros / Cons が本文側に欠落なく残っているか。
- `検討した案` に不採用案と理由が残っているか。
- `TODO(polish)` が残っていないか。
- `TODO(draft)` が残っていないか。
- issue 分割に進めるか。

### 7. Confirm before update

polished body をユーザーへ提示し、確認後だけ Design Doc を更新する。

### 8. Closeout

報告には次を含める。

- polished Design Doc location
- 採用案と採用理由
- 不採用案と不採用理由
- 実行した test / typecheck / proof
- issue 分割へ進めるか、blocked か
- 次に進むべき flow: `draft-issue`
- commit / push / APM pin 更新 / install は未実行であること
