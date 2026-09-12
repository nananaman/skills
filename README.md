# nananaman/skills

nananaman の個人用 agent skills 集です。
APM で配布・インストールし、dotfiles からローカル正本は path、ローカルに置かない正本は full SHA で参照します。

## インストール

この repository の skill は、`apm.yml` で依存として管理する運用を主導線にします。

```yaml
name: my-agent-context
version: 0.1.0
target: claude,agent-skills

dependencies:
  apm:
    - nananaman/skills/meta/apm-usage#<full-sha>
    - nananaman/skills/engineering/implement#<full-sha>
    - nananaman/skills/engineering/review-diff-code#<full-sha>
```

その後、対象の APM project で install します。

```sh
apm install -g
```

review-diff-codeはimplementの簡潔性基準も使うため、両方を導入します。

個別に試す場合は、full SHA を指定して install します。

```sh
apm install -g nananaman/skills/meta/apm-usage#<full-sha>
```

## ディレクトリ方針

利用者が探しやすい用途別分類を主軸にします。

- `engineering/` — コード作業、設計、レビュー、PR 作成など。
- `meta/` — skill 管理、APM 運用、skill 作成・レビューなど。
- `personal/` — chouge 個人の運用デフォルトや作業規約。
- `productivity/` — 汎用的な作業フロー、思考補助、引き継ぎ、学習支援など。
- `sakura-cloud/` — さくらのクラウド関連サービスの作業ランブック。
- `writing/` — 文章執筆、編集、技術文書の推敲など。

## Skill の種類

- `user-invoked`: ユーザーが明示的に呼ぶ skill。作業フローを組み立てる orchestration を担う。
- `model-invoked`: ユーザーが明示して呼ぶことも、タスクに合うと agent が自動参照することもある skill。再利用可能な discipline、policy、domain runbook を持つ。
- `user-invoked` skill は `model-invoked` skill を参照してよい。別の `user-invoked` skill へ委譲するときは Skill tool で起動せず、対象の `SKILL.md` を直接読む。

## Skill 一覧

### Engineering

- **[`prototype`](./engineering/prototype/SKILL.md)** — throwaway artifact や最小の単一 spike で設計上の問いを検証する。
  - Use when: UI・logic・HTML report・文書・diagram・可視化の比較、技術的成立性の実験
  - Type: `model-invoked`
- **[`draft-prd`](./engineering/draft-prd/SKILL.md)** — 新機能・仕様変更の PRD draft を作成する。
  - Use when: 一言アイデア、メモ、会話ログ、既存 issue から PRD の仮説と TODO(polish) を置く
  - Type: `model-invoked`
- **[`polish-prd`](./engineering/polish-prd/SKILL.md)** — PRD draft を作る価値・範囲・成功条件を判断できる文書へ磨く。
  - Use when: PRD の対象ユーザー、やらないこと、作るもの、成功条件、受け入れ条件を詰める
  - Type: `model-invoked`
- **[`draft-design-doc`](./engineering/draft-design-doc/SKILL.md)** — 技術改善・設計変更の Design Doc draft を作成する。
  - Use when: 技術・設計上の問題、PRD 実現に必要な設計判断、複数案の比較検討
  - Type: `model-invoked`
- **[`polish-design-doc`](./engineering/polish-design-doc/SKILL.md)** — Design Doc draft を設計判断と task 分割へ進める文書へ磨く。
  - Use when: 採用案の決定、詳細設計、リスク評価、検討した案、task 分割前の設計 gate
  - Type: `model-invoked`
- **[`task-breakdown`](./engineering/task-breakdown/SKILL.md)** — 合意済みの情報を独立実行可能な task 群へ分解する。
  - Use when: Design Doc、ADR、PRD、会話上の合意、ユーザー説明から tracker 用 task を設計・作成
  - Type: `user-invoked`
- **[`create-plan`](./engineering/create-plan/SKILL.md)** — issue、task、またはユーザーの実装依頼から、grill と調査を経て一時的な実装 plan を作成する。
  - Use when: `create-plan <issue-or-task>`、個別 task やユーザー依頼の実装前設計、`plans/<task>-<slug>.md` の作成
  - Type: `user-invoked`
- **[`review-plan`](./engineering/review-plan/SKILL.md)** — 作成済みの一時実装planをリスクに応じた独立担当が評価し、局所的な修正は影響範囲を確認する。
  - Use when: `create-plan`の完了gate、実装着手前のplan review、別contextでのreadiness判定
  - Type: `model-invoked`
- **[`implement`](./engineering/implement/SKILL.md)** — 実装・簡素化を、必要な検証と完成差分のレビューまで完了させる。
  - Use when: コード、設定、テスト、schema、依存関係、agent指示の作成・変更、振る舞いを保つリファクタリング
  - Type: `model-invoked`
- **[`create-pr`](./engineering/create-pr/SKILL.md)** — 現在の branch からレビューしやすい GitHub draft PR を作成する。
  - Use when: PR 作成、PR template 整理、diff・commit・テスト状況の要約
  - Type: `user-invoked`
- **[`review-diff-code`](./engineering/review-diff-code/SKILL.md)** — コード差分の契約・簡潔性を専門担当が評価し、blind担当が敵対的に検証する。
  - Use when: PRレビュー、実装後の独立した不具合・過剰設計・敵対的レビュー
  - Type: `model-invoked`
- **[`nono-sandbox-maintenance`](./engineering/nono-sandbox-maintenance/SKILL.md)** — nono の拒否を診断し、最小権限の profile patch を作成・検証する。
  - Use when: nono 内だけで起きる filesystem・network・command denial、profile の不足権限調査、policy 修正後の回帰確認
  - Type: `model-invoked`
- **[`tdd`](./engineering/tdd/SKILL.md)** — Red → Green → Refactor を public contract 単位で実行する。
  - Use when: 実行コードのロジック・状態遷移・データ変換・API・型・schemaの処理規則の変更、または明示的なTDD依頼
  - Type: `model-invoked`
- **[`test-writing-style`](./engineering/test-writing-style/SKILL.md)** — テストを仕様として読める検証に整える。
  - Use when: テストの新規追加・修正・レビュー、命名・AAA・1テスト1関心・mock/fake の整理
  - Type: `model-invoked`
- **[`apple-container`](./engineering/apple-container/SKILL.md)** — Apple `container` CLI を実機 version に合わせて安全に操作する。
  - Use when: OCI image の build / run、registry、network・volume・machine 管理、障害調査
  - Type: `model-invoked`

### Meta

- **[`apm-usage`](./meta/apm-usage/SKILL.md)** — APM で agent skill を管理・更新する手順を確認する。
  - Use when: apm.yml 更新、参照方式（path / SHA pin）の確認、global install / dotfiles 連携
  - Type: `model-invoked`
- **[`skill-workbench`](./meta/skill-workbench/SKILL.md)** — agent skill の作成・改善と、本文の過剰制約・振り分け・参照連鎖のレビュー・監査を扱う。
  - Use when: 改善案の提示、新規 skill 作成、構造・routing・lifecycle 改善、skill diff / 全体レビュー、skill inventory audit
  - Type: `model-invoked`
- **[`retrospective-codify`](./meta/retrospective-codify/SKILL.md)** — 再利用可能な知見を、既存規則の削除・限定・更新や適切な設定へ固定する。
  - Use when: 明示的な retrospective / codify 依頼、skill / AGENTS.md / lint rule への知見固定
  - Type: `user-invoked`
- **[`update-skills`](./meta/update-skills/SKILL.md)** — APM skill dependency を最新化する。
  - Use when: apm.yml の pin drift、local 参照先の同期漏れ、複数 skill の一括更新、source-of-truth と展開先の同期確認
  - Type: `user-invoked`

### Personal

- **[`chouge-changelog`](./personal/chouge-changelog/SKILL.md)** — 既存の CHANGES.md を更新する。新規作成は明示依頼時に行う。
  - Use when: CHANGES.md 更新、release note 下書き、PR / commit 内容の変更履歴化
  - Type: `model-invoked`
- **[`chouge-git`](./personal/chouge-git/SKILL.md)** — chouge 個人の Git/GitHub 運用規約を適用する。
  - Use when: commit、branch、push、PR 作成・更新
  - Type: `model-invoked`
- **[`merge-closeout`](./personal/merge-closeout/SKILL.md)** — PR マージ後の default branch 同期と retrospective を一度に行う。
  - Use when: PR マージ後の local 同期と知見の棚卸し
  - Type: `user-invoked`

### Productivity

- **[`grilling`](./productivity/grilling/SKILL.md)** — 計画、設計、PRD、Design Doc、issue を一問ずつ詰める reusable discipline。
  - Use when: 計画や設計の明示的な検討依頼、他 skill からの曖昧さ・未決定・依存する判断の解消
  - Type: `model-invoked`
- **[`handoff`](./productivity/handoff/SKILL.md)** — 現在の会話を別の agent が引き継げる handoff document に圧縮する。
  - Use when: セッション引き継ぎ、長い会話の圧縮、別 agent への作業移管
  - Type: `user-invoked`
- **[`improve-agent-prompt`](./productivity/improve-agent-prompt/SKILL.md)** — GPT-6 Astra を基準に、agent向け指示の不要な停止・過剰手順・競合を診断・改善する。
  - Use when: system prompt、agent instructions、tool description、AGENTS.md、skill 本文の agent-facing contract、prompt stack、context 配置の改善（skill の作成・構造・振り分け・本文を含むレビューは `skill-workbench`）
  - Type: `model-invoked`

### Sakura Cloud

- **[`sakura-cloud-eventbus`](./sakura-cloud/eventbus/SKILL.md)** — EventBus の実行設定、スケジュール、イベントトリガーを扱う。
  - Use when: EventBus 設計、Schedule / Trigger 作成、SimpleMQ / シンプル通知連携
  - Type: `model-invoked`
- **[`sakura-cloud-webaccel`](./sakura-cloud/webaccel/SKILL.md)** — ウェブアクセラレータのサイト設定・運用を扱う。
  - Use when: サイト追加、独自ドメイン / SSL 設定、キャッシュ削除 / オリジンガード
  - Type: `model-invoked`
- **[`sakura-cloud-workflows`](./sakura-cloud/workflows/SKILL.md)** — Workflows の YAML 作成、デバッグ、API 操作を扱う。
  - Use when: YAML 作成、式のデバッグ、実行履歴確認 / キャンセル
  - Type: `model-invoked`

### Writing

- **[`japanese-tech-writing`](./writing/japanese-tech-writing/SKILL.md)** — 日本語の技術文書・PRD・Design Doc・書籍の共通文章規範。書籍の構成・演出は必要時だけ参照する。
  - Use when: 技術書・記事の執筆、草稿の推敲、日本語技術文書の構成レビュー
  - Type: `model-invoked`

## 運用

- dotfiles 側には global skill の install 一覧として `apm/apm.yml` だけを置く。
- skill 本体はこの repository を source of truth にする。
- dotfiles から参照するときは、ローカルに置く正本を path、ローカルに置かない正本を full SHA で指定する。
- skill 更新後に配布する場合は、`skill-workbench` で変更に必要な差分レビューを行ってから、この repository で commit / push し、path 参照なら参照先 repository、pin 参照なら dotfiles 側の SHA を更新する。
- commit / push / 参照先または pin の更新 / `apm install -g` はユーザーが明示依頼した場合だけ行う。
