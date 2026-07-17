---
name: polish-prd
description: PRD draft を、作る価値・範囲・成功条件を人間が判断できる PRD に磨く。PM 的な問いを一つずつ grill し、TODO(polish) を解消する。技術設計、Design Doc 作成、issue 作成、実装、レビューだけの依頼では使わない。
---

# Polish PRD

PRD draft を「この機能を作る価値・範囲・成功条件を判断できる文書」に磨く。
PM 的な問いを一つずつ grill し、要求の曖昧さを潰す。

## Contract

polished PRD は、次を満たす。

- 概要とゴールが端的である。
- やらないことが明確である。
- 対象ユーザー / 利用者が明確である。
- なぜ作るかが明確である。
- 複数のプロダクト案が比較され、採用案が `作るもの` に昇格し、不採用案と理由が `検討した案` に残っている。
- 作るものが要求として具体的である。
- 受け入れ条件が observable である。
- 成功条件が判断可能である。
- 要求に関する `TODO(polish)` が残っていない。
- 実装設計に踏み込んでいない。

## 併用する skill

この PRD を対象に、`japanese-tech-writing` skill を併用して `grilling` session を実行する。

この skill は PRD の構造と完了条件を定める。
`grilling` は曖昧さを一問ずつ潰す手順を定める。
`japanese-tech-writing` は文章品質を定める。

## Safety

- この skill では `git commit`、`git push`、APM pin 更新、skill install を実行しない。
- この skill では Design Doc / issue / 実装 diff を作らない。
- PRD 更新前に polished body をユーザーへ提示し、確認後だけ更新する。

## Workflow

### 1. Load context

対象 PRD draft を読む。
repo-local 設定があれば読む。

```text
docs/agents/engineering-flow.md
docs/agents/domain.md
```

PRD が存在しない場合は `draft-prd` を提案して止める。
`TODO(draft)` が残っている、または draft が blocked の場合は polish へ進まず、`draft-prd` で draft gate を解消するよう報告して止める。

### 2. Confirm scope

PRD は新機能・仕様変更の要求判断に使う。
技術改善だけの文書なら `draft-design-doc` / `polish-design-doc` を提案する。

### 3. Grill one question at a time

一度に一つずつ問いを立てる。
コードベースや既存 docs から答えられることは、ユーザーに聞く前に調べる。
draft に残った `TODO(polish)` と、polished gate を阻害する具体的な不足・矛盾を優先する。
draft で根拠とともに確定している内容は一律に問い直さない。

不足・矛盾がある場合に詰める問い:

- 誰の問題か。
- その人は今どう困っているか。
- この機能で何ができるようになるか。
- 比較する案は揃っているか。どの案を採用し、なぜか。
- 何はやらないか。
- 作る価値は何か。
- 成功は何で判断するか。
- 成功条件は観測または判断できるか。
- 受け入れ条件はテスト・レビューで確認できるか。
- 要求と設計が混ざっていないか。

### 4. Decide adopted product approach

`検討した案` にある候補を、draft で確定した問題・制約・成功条件に照らして比較し、採用案を決める。

- 採用案は `作るもの` に反映する。
- 採用案のユーザー体験、提供価値、成立条件、重要な Pros / Cons を `作るもの` と `採用理由` へ欠落なく反映してから、その subsection を `検討した案` から外す。
- `検討した案` には不採用案だけを残し、各案の `Conclusion` に不採用理由を書く。
- 採用案を決められない場合は polished にせず blocked として報告する。

### 5. Rewrite PRD

`../draft-prd/assets/prd-template.md` の構造に合わせて PRD を更新する。

- template の `TODO(draft)` は draft 作成用の指示であり、polished PRD に転記しない。
- polished gate を満たした PRD は `状態: Polished` に更新する。
- `TODO(polish)` コメントは polished PRD に残さない。
- 要求に関する未解決事項が残る場合は polished にしない。
- 設計判断は Design Doc へ送る内容として分離し、PRD には書きすぎない。
- issue 分割や実装方針は書かない。

### 6. Validate polished gate

更新前に以下を自己確認する。

- 人間が作る価値・範囲・成功条件を判断できるか。
- `やらないこと` が scope creep を止められるか。
- 対象ユーザー / 利用者が広すぎないか。
- 採用案が `作るもの` に反映され、`検討した案` に重複して残っていないか。
- 採用案のユーザー体験、提供価値、成立条件、重要な Pros / Cons が本文側に欠落なく残っているか。
- `検討した案` に不採用案と理由が残っているか。
- `作るもの` が要求として読めるか。
- 受け入れ条件が observable か。
- 成功条件が判断可能か。
- `TODO(polish)` が残っていないか。
- `TODO(draft)` が残っていないか。
- 実装設計に踏み込んでいないか。

### 7. Confirm before update

polished body をユーザーへ提示し、確認後だけ PRD を更新する。

### 8. Closeout

報告には次を含める。

- polished PRD location
- 採用案と採用理由
- 不採用案と不採用理由
- 解消した TODO / 判断
- Design Doc に送るべき設計論点があればその要約
- 次に進むべき flow: `draft-design-doc` / `draft-issue`
- commit / push / APM pin 更新 / install は未実行であること
