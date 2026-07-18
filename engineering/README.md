# Engineering Skills

コード作業、設計文書、issue 整理、レビュー、PR 作成に使う skill 群です。
PRD、Design Doc、issue を draft から polish し、TDD による実装、テスト記述、実装後レビュー、レビューしやすい PR 作成までの導線を扱います。

## どの Skill を使うか

- Web・mobile/native の UI や logic の複数案を操作して比較する → [`prototype`](./prototype/SKILL.md)
- リポジトリごとの engineering flow を初期設定する → [`setup-engineering-flow`](./setup-engineering-flow/SKILL.md)
- 新機能・仕様変更の PRD draft を作る → [`draft-prd`](./draft-prd/SKILL.md)
- PRD を作る価値・範囲・成功条件を判断できる文書に磨く → [`polish-prd`](./polish-prd/SKILL.md)
- 技術改善・設計変更の Design Doc draft を作る → [`draft-design-doc`](./draft-design-doc/SKILL.md)
- Design Doc を設計判断・issue 分割へ進める文書に磨く → [`polish-design-doc`](./polish-design-doc/SKILL.md)
- 実装前の issue draft を作る → [`draft-issue`](./draft-issue/SKILL.md)
- issue を実装設計契約に磨く → [`polish-issue`](./polish-issue/SKILL.md)
- よほどの微修正ではないコード変更を TDD で進める → [`tdd`](./tdd/SKILL.md)
- テストの命名・構造・assertion・mock/fake を整える → [`test-writing-style`](./test-writing-style/SKILL.md)
- 現在の branch から draft PR を作る → [`create-pr`](./create-pr/SKILL.md)
- diff / branch diff / PR diff を厳しめに見る → [`review-diff-code`](./review-diff-code/SKILL.md)
- commit 前に Hunk で人間レビューを依頼する → [`hunk-human-review`](./hunk-human-review/SKILL.md)
- sandbox runtime 起因の ghost dotfiles、mount artifact、workflow scope 不足を診断する → [`sandbox-runtime`](./sandbox-runtime/SKILL.md)
- ast-grep を project-local な構造 lint / rewrite として運用する → [`ast-grep-practice`](./ast-grep-practice/SKILL.md)

## 典型フロー

1. 初回は `setup-engineering-flow` で issue tracker、PRD、Design Doc の配置を記録する。
2. 新機能・仕様変更は `draft-prd` → `polish-prd` で要求を固める。
3. 技術改善・設計変更、または PRD 実現に設計判断が必要な変更は `draft-design-doc` → `polish-design-doc` で設計を固める。
4. 実装作業単位は `draft-issue` → `polish-issue` で実装設計契約にする。
5. よほどの微修正でない変更は、`tdd` で RED → GREEN → Refactor の順に進める。
6. テストを書くときは、`test-writing-style` で既存テスト文化と読みやすさを揃える。
7. 実装後、`review-diff-code` で差分を確認する。
8. 指摘を直し、必要なテストや確認コマンドを実行する。
9. `create-pr` で diff・commit・テスト状況を整理した draft PR を作る。

## Skill 一覧

- **[`prototype`](./prototype/SKILL.md)** — 複数案を操作して比較できる throwaway prototype で設計上の問いを検証する。
  - Use when: Web・mobile/native の UI 比較、状態遷移・データ構造・API の操作検証
  - Type: `model-invoked`
- **[`setup-engineering-flow`](./setup-engineering-flow/SKILL.md)** — リポジトリごとの engineering flow を初期設定する。
  - Use when: issue tracker、PRD / Design Doc 配置、local markdown issue 採番、AGENTS.md / CLAUDE.md 参照 block の設定
  - Type: `user-invoked`
- **[`draft-prd`](./draft-prd/SKILL.md)** — 新機能・仕様変更の PRD draft を作成する。
  - Use when: 一言アイデア、メモ、会話ログ、既存 issue から PRD の仮説と TODO(polish) を置く
  - Type: `model-invoked`
- **[`polish-prd`](./polish-prd/SKILL.md)** — PRD draft を作る価値・範囲・成功条件を判断できる文書へ磨く。
  - Use when: PRD の対象ユーザー、やらないこと、作るもの、成功条件、受け入れ条件を詰める
  - Type: `model-invoked`
- **[`draft-design-doc`](./draft-design-doc/SKILL.md)** — 技術改善・設計変更の Design Doc draft を作成する。
  - Use when: 技術・設計上の問題、PRD 実現に必要な設計判断、複数案の比較検討
  - Type: `model-invoked`
- **[`polish-design-doc`](./polish-design-doc/SKILL.md)** — Design Doc draft を設計判断と issue 分割へ進める文書へ磨く。
  - Use when: 採用案の決定、詳細設計、リスク評価、検討した案、issue 分割前の設計 gate
  - Type: `model-invoked`
- **[`draft-issue`](./draft-issue/SKILL.md)** — 実装前の issue draft を作成する。
  - Use when: polished PRD / Design Doc またはユーザー説明から、仮説と TODO(polish) 付き issue を作る
  - Type: `model-invoked`
- **[`polish-issue`](./polish-issue/SKILL.md)** — issue を実装設計契約に磨く。
  - Use when: issue だけで実装に入れるように、目的、現状、設計方針、変更対象、テスト方針、完了条件を詰める
  - Type: `model-invoked`
- **[`create-pr`](./create-pr/SKILL.md)** — 現在の branch からレビューしやすい GitHub draft PR を作成する。
  - Use when: PR 作成、PR template 整理、diff・commit・テスト状況の要約
  - Type: `user-invoked`
- **[`review-diff-code`](./review-diff-code/SKILL.md)** — 現在の diff / branch diff / PR diff を3つの独立contextで批判的にレビューする。
  - Use when: PR 前レビュー、実装後セルフレビュー、別モデルレビュー、adversarial review
  - Type: `model-invoked`
- **[`hunk-human-review`](./hunk-human-review/SKILL.md)** — commit 前に Hunk TUI で人間レビューを依頼する。
  - Use when: Hunk で人間に確認してもらう、commit 前に未ステージ差分を人間へ見せる、レビュー完了後に Hunk コメントを回収する
  - Type: `model-invoked`
- **[`sandbox-runtime`](./sandbox-runtime/SKILL.md)** — Anthropic Sandbox Runtime 起因の ghost dotfiles や mount artifact を診断する。
  - Use when: sandbox 実行後の想定外 untracked files、read-only filesystem、workflow scope 不足、gh auth refresh 失敗の診断
  - Type: `model-invoked`
- **[`ast-grep-practice`](./ast-grep-practice/SKILL.md)** — ast-grep を project-local な構造 lint / rewrite として運用する。
  - Use when: 既存 linter で表現しにくい AST パターンの rule draft、rule-tests、sgconfig.yml、検証コマンド、kind 名・rule 例の確認
  - Type: `model-invoked`
- **[`tdd`](./tdd/SKILL.md)** — Red → Green → Refactor を public contract 単位で実行する。
  - Use when: 機能追加、バグ修正、仕様変更、リファクタリング、よほどの微修正ではないコード変更
  - Type: `model-invoked`
- **[`test-writing-style`](./test-writing-style/SKILL.md)** — テストを仕様として読める検証に整える。
  - Use when: テストの新規追加・修正・レビュー、命名・AAA・1テスト1関心・mock/fake の整理
  - Type: `model-invoked`
