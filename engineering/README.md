# Engineering Skills

コード作業、設計文書、task 分解、一時 plan、実装、レビュー、PR 作成に使う skill 群です。
PRD、Design Doc、独立実行可能な task、実装用 plan、実装、TDD、実装後レビュー、レビューしやすいPR作成までの導線を扱います。

## どの Skill を使うか

- UI・logic・文書・可視化などを比較する、または単一 spike で成立性を確かめる → [`prototype`](./prototype/SKILL.md)
- リポジトリごとの engineering flow を初期設定する → [`setup-engineering-flow`](./setup-engineering-flow/SKILL.md)
- 新機能・仕様変更の PRD draft を作る → [`draft-prd`](./draft-prd/SKILL.md)
- PRD を作る価値・範囲・成功条件を判断できる文書に磨く → [`polish-prd`](./polish-prd/SKILL.md)
- 技術改善・設計変更の Design Doc draft を作る → [`draft-design-doc`](./draft-design-doc/SKILL.md)
- Design Doc を設計判断・task 分割へ進める文書に磨く → [`polish-design-doc`](./polish-design-doc/SKILL.md)
- 合意済みの要求・設計を独立実行可能な task 群へ分解する → [`task-breakdown`](./task-breakdown/SKILL.md)
- issue、task、またはユーザーの実装依頼から、grill 後に一時的な実装 plan を作る → [`create-plan`](./create-plan/SKILL.md)
- 作成済みの実装 plan を検討漏れと不要な複雑性の観点で独立評価する → [`review-plan`](./review-plan/SKILL.md)
- コードや設定などの実装を、検証、簡素化、完成差分のレビューまで通して完了する → [`implement`](./implement/SKILL.md)
- 今回の作業に属し、検証に成功したコード差分を、必要な場合だけ振る舞いを保ったまま簡素化する → [`simplify-code`](./simplify-code/SKILL.md)
- 実行コードのロジック・状態遷移・データ変換・処理規則の変更を TDD で進める → [`tdd`](./tdd/SKILL.md)
- テストの命名・構造・assertion・mock/fake を整える → [`test-writing-style`](./test-writing-style/SKILL.md)
- 現在の branch から draft PR を作る → [`create-pr`](./create-pr/SKILL.md)
- diff / branch diff / PR diff を厳しめに見る → [`review-diff-code`](./review-diff-code/SKILL.md)
- local差分を変更前後と因果順で解説する画面を作る → [`explain-diff`](./explain-diff/SKILL.md)
- commit 前に Hunk で人間レビューを依頼する → [`hunk-human-review`](./hunk-human-review/SKILL.md)
- sandbox runtime 起因の ghost dotfiles、mount artifact、workflow scope 不足を診断する → [`sandbox-runtime`](./sandbox-runtime/SKILL.md)
- nono の拒否を診断し、最小権限の profile patch を作成・検証する → [`nono-sandbox-maintenance`](./nono-sandbox-maintenance/SKILL.md)
- ast-grep を project-local な構造 lint / rewrite として運用する → [`ast-grep-practice`](./ast-grep-practice/SKILL.md)
- Apple `container` CLI で OCI image・container・network・volume・machine を操作する → [`apple-container`](./apple-container/SKILL.md)
- Realtime API の音声対話で観測された症状から system prompt の技法を選び、診断・改善する → [`realtime-prompt-review`](./realtime-prompt-review/SKILL.md)

## 典型フロー

1. 継続運用の規則が必要なら `setup-engineering-flow` で issue tracker、PRD、Design Doc / ADR、一時 plan の配置を記録する。`task-breakdown` にはこの設定が必須だが、`create-plan` は設定なしでも実行できる。
2. 新機能・仕様変更は `draft-prd` → `polish-prd` で要求を固める。
3. 技術改善・設計変更、または PRD 実現に設計判断が必要な変更は `draft-design-doc` → `polish-design-doc` で設計を固める。
4. 合意済みの要求・設計は `task-breakdown` で独立実行可能な issue 群へ分ける。
5. issue、task、またはユーザーの実装依頼を受けたら `create-plan` で grill と調査を行い、untracked の一時 plan を作る。`create-plan`は完了前に`review-plan`を自動実行し、検討漏れと不要な複雑性のblockerを解消する。
6. コード、設定、テスト、schema、依存関係、agent 指示の実装には`implement`を使い、必要な専門 skill、検証、簡素化の判断、完成差分のレビューまで完了する。
7. 大きなlocal差分を人間へ説明するときは、必要に応じて `explain-diff` で変更の物語と根拠を確認する画面を作る。
8. レビュー後、plan 原文を commit body に保存して plan file を削除する。
9. `create-pr` で diff・commit・テスト状況と折りたたんだ plan を含む draft PR を作る。

## Skill 一覧

- **[`prototype`](./prototype/SKILL.md)** — throwaway artifact や最小の単一 spike で設計上の問いを検証する。
  - Use when: UI・logic・HTML report・文書・diagram・可視化の比較、技術的成立性の実験
  - Type: `model-invoked`
- **[`setup-engineering-flow`](./setup-engineering-flow/SKILL.md)** — リポジトリごとの engineering flow を初期設定する。
  - Use when: issue tracker、PRD / Design Doc / ADR、一時 plan 配置、local markdown issue 採番、AGENTS.md / CLAUDE.md 参照 block の設定
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
- **[`polish-design-doc`](./polish-design-doc/SKILL.md)** — Design Doc draft を設計判断と task 分割へ進める文書へ磨く。
  - Use when: 採用案の決定、詳細設計、リスク評価、検討した案、task 分割前の設計 gate
  - Type: `model-invoked`
- **[`task-breakdown`](./task-breakdown/SKILL.md)** — 合意済みの情報を独立実行可能な task 群へ分解する。
  - Use when: Design Doc、ADR、PRD、会話上の合意、ユーザー説明から tracker 用 task を設計・作成
  - Type: `user-invoked`
- **[`create-plan`](./create-plan/SKILL.md)** — issue、task、またはユーザーの実装依頼から、grill と調査を経て一時的な実装 plan を作成する。
  - Use when: `create-plan <issue-or-task>`、個別 task やユーザー依頼の実装前設計、`plans/<task>-<slug>.md` の作成
  - Type: `user-invoked`
- **[`review-plan`](./review-plan/SKILL.md)** — 作成済みの一時実装planを、実現可能性と単純性のfresh reviewerで独立評価する。
  - Use when: `create-plan`の完了gate、実装着手前のplan review、別contextでのreadiness判定
  - Type: `model-invoked`
- **[`implement`](./implement/SKILL.md)** — 実装を検証、簡素化、完成差分のレビューまで通して完了させる。
  - Use when: コード、設定、テスト、schema、依存関係、agent 指示の作成または変更
  - Type: `model-invoked`
- **[`simplify-code`](./simplify-code/SKILL.md)** — 今回の作業に属し、検証に成功したコード差分を、必要な場合だけ振る舞いを保ったまま簡素化する。
  - Use when: 実装後に簡素化の必要性を判断するとき、明示的な簡素化や振る舞いを変えないリファクタリング
  - Type: `model-invoked`
- **[`create-pr`](./create-pr/SKILL.md)** — 現在の branch からレビューしやすい GitHub draft PR を作成する。
  - Use when: PR 作成、PR template 整理、diff・commit・テスト状況の要約
  - Type: `user-invoked`
- **[`review-diff-code`](./review-diff-code/SKILL.md)** — 現在のdiff / branch diff / PR diffをrisk-based reviewerとblind Adversarialで一度評価する。
  - Use when: PR 前レビュー、実装後セルフレビュー、別モデルレビュー、adversarial review
  - Type: `model-invoked`
- **[`explain-diff`](./explain-diff/SKILL.md)** — local差分を変更前後と因果順で解説する人間向けHTMLを生成する。
  - Use when: 大きな未コミット差分の説明、変更グループごとの確認・コメント、LAN配信、元セッション向けfeedback作成
  - Type: `user-invoked`
- **[`hunk-human-review`](./hunk-human-review/SKILL.md)** — commit 前に Hunk TUI で人間レビューを依頼する。
  - Use when: Hunk で人間に確認してもらう、commit 前に未ステージ差分を人間へ見せる、レビュー完了後に Hunk コメントを回収する
  - Type: `model-invoked`
- **[`sandbox-runtime`](./sandbox-runtime/SKILL.md)** — Anthropic Sandbox Runtime 起因の ghost dotfiles や mount artifact を診断する。
  - Use when: sandbox 実行後の想定外 untracked files、read-only filesystem、workflow scope 不足、gh auth refresh 失敗の診断
  - Type: `model-invoked`
- **[`nono-sandbox-maintenance`](./nono-sandbox-maintenance/SKILL.md)** — nono の拒否を診断し、最小権限の profile patch を作成・検証する。
  - Use when: nono 内だけで起きる filesystem・network・command denial、profile の不足権限調査、policy 修正後の回帰確認
  - Type: `model-invoked`
- **[`ast-grep-practice`](./ast-grep-practice/SKILL.md)** — ast-grep を project-local な構造 lint / rewrite として運用する。
  - Use when: 既存 linter で表現しにくい AST パターンの rule draft、rule-tests、sgconfig.yml、検証コマンド、kind 名・rule 例の確認
  - Type: `model-invoked`
- **[`tdd`](./tdd/SKILL.md)** — Red → Green → Refactor を public contract 単位で実行する。
  - Use when: 実行コードのロジック・状態遷移・データ変換・API・型・schemaの処理規則の変更、または明示的なTDD依頼
  - Type: `model-invoked`
- **[`test-writing-style`](./test-writing-style/SKILL.md)** — テストを仕様として読める検証に整える。
  - Use when: テストの新規追加・修正・レビュー、命名・AAA・1テスト1関心・mock/fake の整理
  - Type: `model-invoked`
- **[`apple-container`](./apple-container/SKILL.md)** — Apple `container` CLI を実機 version に合わせて安全に操作する。
  - Use when: OCI image の build / run、registry、network・volume・machine 管理、障害調査
  - Type: `model-invoked`
- **[`realtime-prompt-review`](./realtime-prompt-review/SKILL.md)** — Realtime API の音声対話で観測された症状から system prompt の介入を選び、診断・改善する。
  - Use when: 意図しない言語切替、冗長・平板な発話、咳・無音・背景音への応答、発音、tool 誤選択、会話 flow・human escalation の逸脱
  - Type: `user-invoked`
