# Engineering Skills

コード作業、レビュー、PR 作成に使う skill 群です。
TDD による実装、テスト記述、実装後レビュー、レビューしやすい PR 作成の導線を扱います。

## どの Skill を使うか

- よほどの微修正ではないコード変更を TDD で進める → [`tdd`](./tdd/SKILL.md)
- テストの命名・構造・assertion・mock/fake を整える → [`test-writing-style`](./test-writing-style/SKILL.md)
- 現在の branch から draft PR を作る → [`create-pr`](./create-pr/SKILL.md)
- diff / branch diff / PR diff を厳しめに見る → [`review-diff-code`](./review-diff-code/SKILL.md)
- sandbox runtime 起因の ghost dotfiles、mount artifact、workflow scope 不足を診断する → [`sandbox-runtime`](./sandbox-runtime/SKILL.md)

## 典型フロー

1. よほどの微修正でない変更は、`tdd` で RED → GREEN → Refactor の順に進める。
2. テストを書くときは、`test-writing-style` で既存テスト文化と読みやすさを揃える。
3. 実装後、`review-diff-code` で差分を確認する。
4. 指摘を直し、必要なテストや確認コマンドを実行する。
5. `create-pr` で diff・commit・テスト状況を整理した draft PR を作る。

## Skill 一覧

- **[`create-pr`](./create-pr/SKILL.md)** — 現在の branch からレビューしやすい GitHub draft PR を作成する。
  - Use when: PR 作成、PR template 整理、diff・commit・テスト状況の要約
  - Type: `user-invoked`
- **[`review-diff-code`](./review-diff-code/SKILL.md)** — 現在の diff / branch diff / PR diff を厳しめにレビューする。
  - Use when: PR 前レビュー、実装後セルフレビュー、別モデルレビュー
  - Type: `model-invoked`
- **[`sandbox-runtime`](./sandbox-runtime/SKILL.md)** — Anthropic Sandbox Runtime 起因の ghost dotfiles や mount artifact を診断する。
  - Use when: sandbox 実行後の想定外 untracked files、read-only filesystem、workflow scope 不足、gh auth refresh 失敗の診断
  - Type: `model-invoked`
- **[`tdd`](./tdd/SKILL.md)** — Red → Green → Refactor を public contract 単位で実行する。
  - Use when: 機能追加、バグ修正、仕様変更、リファクタリング、よほどの微修正ではないコード変更
  - Type: `model-invoked`
- **[`test-writing-style`](./test-writing-style/SKILL.md)** — テストを仕様として読める検証に整える。
  - Use when: テストの新規追加・修正・レビュー、命名・AAA・1テスト1関心・mock/fake の整理
  - Type: `model-invoked`
