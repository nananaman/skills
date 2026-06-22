# Engineering Skills

コード作業、レビュー、PR 作成に使う skill 群です。
実装前後の品質確認と、レビューしやすい PR 作成の導線を扱います。

## どの Skill を使うか

- 現在の branch から draft PR を作る → [`create-pr`](./create-pr/SKILL.md)
- diff / branch diff / PR diff を厳しめに見る → [`review-diff-code`](./review-diff-code/SKILL.md)
- 実装後に correctness・security・maintainability を確認する → [`review-diff-code`](./review-diff-code/SKILL.md)

## 典型フロー

1. 実装後、`review-diff-code` で差分を確認する。
2. 指摘を直し、必要なテストや確認コマンドを実行する。
3. `create-pr` で diff・commit・テスト状況を整理した draft PR を作る。

## Skill 一覧

- **[`create-pr`](./create-pr/SKILL.md)** — 現在の branch からレビューしやすい GitHub draft PR を作成する。
  - Use when: PR 作成、PR template 整理、diff・commit・テスト状況の要約
  - Type: `user-invoked`
- **[`review-diff-code`](./review-diff-code/SKILL.md)** — 現在の diff / branch diff / PR diff を厳しめにレビューする。
  - Use when: PR 前レビュー、実装後セルフレビュー、別モデルレビュー
  - Type: `model-invoked`
