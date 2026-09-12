# Engineering Skills

コード作業、設計文書、task 分解、一時 plan、実装、レビュー、PR 作成に使う skill 群です。
PRD、Design Doc、独立実行可能な task、実装用 plan、実装、TDD、実装後レビュー、レビューしやすいPR作成までの導線を扱います。

## どの Skill を使うか

- UI・logic・文書・可視化などを比較する、または単一 spike で成立性を確かめる → [`prototype`](./prototype/SKILL.md)
- 新機能・仕様変更の PRD draft を作る → [`draft-prd`](./draft-prd/SKILL.md)
- PRD を作る価値・範囲・成功条件を判断できる文書に磨く → [`polish-prd`](./polish-prd/SKILL.md)
- 技術改善・設計変更の Design Doc draft を作る → [`draft-design-doc`](./draft-design-doc/SKILL.md)
- Design Doc を設計判断・task 分割へ進める文書に磨く → [`polish-design-doc`](./polish-design-doc/SKILL.md)
- 合意済みの要求・設計を独立実行可能な task 群へ分解する → [`task-breakdown`](./task-breakdown/SKILL.md)
- issue、task、またはユーザーの実装依頼から、grill 後に一時的な実装 plan を作る → [`create-plan`](./create-plan/SKILL.md)
- 作成済みの実装 plan を検討漏れと不要な複雑性の観点で独立評価する → [`review-plan`](./review-plan/SKILL.md)
- コードを簡素化する → [`implement`](./implement/SKILL.md)
- コードや設定などの実装を、必要な検証と完成差分のレビューまで完了する → [`implement`](./implement/SKILL.md)
- 実行コードのロジック・状態遷移・データ変換・処理規則の変更を TDD で進める → [`tdd`](./tdd/SKILL.md)
- テストの命名・構造・assertion・mock/fake を整える → [`test-writing-style`](./test-writing-style/SKILL.md)
- 現在の branch から draft PR を作る → [`create-pr`](./create-pr/SKILL.md)
- diff / branch diff / PR diff を厳しめに見る → [`review-diff-code`](./review-diff-code/SKILL.md)
- nono の拒否を診断し、最小権限の profile patch を作成・検証する → [`nono-sandbox-maintenance`](./nono-sandbox-maintenance/SKILL.md)
- Apple `container` CLI で OCI image・container・network・volume・machine を操作する → [`apple-container`](./apple-container/SKILL.md)

## 作業の進め方

依頼された成果に応じてskillを選ぶ。通常の実装・簡素化は `implement` が探索、変更、検証、レビュー、指摘修正まで進める。
意味のあるコード差分は `review-diff-code` の専門担当が契約と簡潔性を確認し、blind担当が敵対的に検証する。

要求・設計を文書化する依頼ではdraft/polish、タスク分割ではtask-breakdown、個別の計画作成ではcreate-planを使う。
これらをすべての実装に前置しない。計画作成を依頼された場合は独立したreview-planまで完了する。
PR作成の依頼ではcreate-prを使い、完成差分と検証結果に基づくdraft PRを作る。

## Skill 一覧

- **[`prototype`](./prototype/SKILL.md)** — throwaway artifact や最小の単一 spike で設計上の問いを検証する。
  - Use when: UI・logic・HTML report・文書・diagram・可視化の比較、技術的成立性の実験
  - Type: `model-invoked`
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
- **[`review-plan`](./review-plan/SKILL.md)** — 作成済みの一時実装planをリスクに応じた独立担当が評価し、局所的な修正は影響範囲を確認する。
  - Use when: `create-plan`の完了gate、実装着手前のplan review、別contextでのreadiness判定
  - Type: `model-invoked`
- **[`implement`](./implement/SKILL.md)** — 実装・簡素化を、必要な検証と完成差分のレビューまで完了させる。
  - Use when: コード、設定、テスト、schema、依存関係、agent指示の作成・変更、振る舞いを保つリファクタリング
  - Type: `model-invoked`
- **[`create-pr`](./create-pr/SKILL.md)** — 現在の branch からレビューしやすい GitHub draft PR を作成する。
  - Use when: PR 作成、PR template 整理、diff・commit・テスト状況の要約
  - Type: `user-invoked`
- **[`review-diff-code`](./review-diff-code/SKILL.md)** — コード差分の契約・簡潔性を専門担当が評価し、blind担当が敵対的に検証する。
  - Use when: PRレビュー、実装後の独立した不具合・過剰設計・敵対的レビュー
  - Type: `model-invoked`
- **[`nono-sandbox-maintenance`](./nono-sandbox-maintenance/SKILL.md)** — nono の拒否を診断し、最小権限の profile patch を作成・検証する。
  - Use when: nono 内だけで起きる filesystem・network・command denial、profile の不足権限調査、policy 修正後の回帰確認
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
