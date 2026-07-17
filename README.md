# nananaman/skills

nananaman の個人用 agent skills 集です。
APM で配布・インストールし、dotfiles から full SHA で pin して使います。

## インストール

この repository の skill は、`apm.yml` で依存として管理する運用を主導線にします。

```yaml
name: my-agent-context
version: 0.1.0
target: claude,agent-skills

dependencies:
  apm:
    - nananaman/skills/meta/apm-usage#<full-sha>
    - nananaman/skills/engineering/review-diff-code#<full-sha>
```

その後、対象の APM project で install します。

```sh
apm install -g
```

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
- `user-invoked` skill は `model-invoked` skill を参照してよいが、別の `user-invoked` skill を内部から起動しない。

## Skill 一覧

### Engineering

- **[`setup-engineering-flow`](./engineering/setup-engineering-flow/SKILL.md)** — リポジトリごとの engineering flow を初期設定する。
  - Use when: issue tracker、PRD / Design Doc 配置、local markdown issue 採番、AGENTS.md / CLAUDE.md 参照 block の設定
  - Type: `user-invoked`
- **[`draft-prd`](./engineering/draft-prd/SKILL.md)** — 新機能・仕様変更の PRD draft を作成する。
  - Use when: 一言アイデア、メモ、会話ログ、既存 issue から PRD の仮説と TODO(polish) を置く
  - Type: `model-invoked`
- **[`polish-prd`](./engineering/polish-prd/SKILL.md)** — PRD draft を作る価値・範囲・成功条件を判断できる文書へ磨く。
  - Use when: PRD の対象ユーザー、やらないこと、作るもの、成功条件、受け入れ条件を詰める
  - Type: `model-invoked`
- **[`draft-design-doc`](./engineering/draft-design-doc/SKILL.md)** — 技術改善・設計変更の Design Doc draft を作成する。
  - Use when: 技術・設計上の問題、PRD 実現に必要な設計判断、複数案の比較検討
  - Type: `model-invoked`
- **[`polish-design-doc`](./engineering/polish-design-doc/SKILL.md)** — Design Doc draft を設計判断と issue 分割へ進める文書へ磨く。
  - Use when: 採用案の決定、詳細設計、リスク評価、検討した案、issue 分割前の設計 gate
  - Type: `model-invoked`
- **[`draft-issue`](./engineering/draft-issue/SKILL.md)** — 実装前の issue draft を作成する。
  - Use when: polished PRD / Design Doc またはユーザー説明から、仮説と TODO(polish) 付き issue を作る
  - Type: `model-invoked`
- **[`polish-issue`](./engineering/polish-issue/SKILL.md)** — issue を実装設計契約に磨く。
  - Use when: issue だけで実装に入れるように、目的、現状、設計方針、変更対象、テスト方針、完了条件を詰める
  - Type: `model-invoked`
- **[`create-pr`](./engineering/create-pr/SKILL.md)** — 現在の branch からレビューしやすい GitHub draft PR を作成する。
  - Use when: PR 作成、PR template 整理、diff・commit・テスト状況の要約
  - Type: `user-invoked`
- **[`review-diff-code`](./engineering/review-diff-code/SKILL.md)** — 現在の diff / branch diff / PR diff を3つの独立contextで批判的にレビューする。
  - Use when: PR 前レビュー、実装後セルフレビュー、別モデルレビュー、adversarial review
  - Type: `model-invoked`
- **[`hunk-human-review`](./engineering/hunk-human-review/SKILL.md)** — commit 前に Hunk TUI で人間レビューを依頼する。
  - Use when: Hunk で人間に確認してもらう、commit 前に未ステージ差分を人間へ見せる、レビュー完了後に Hunk コメントを回収する
  - Type: `model-invoked`
- **[`sandbox-runtime`](./engineering/sandbox-runtime/SKILL.md)** — Anthropic Sandbox Runtime 起因の ghost dotfiles や mount artifact を診断する。
  - Use when: sandbox 実行後の想定外 untracked files、read-only filesystem、workflow scope 不足、gh auth refresh 失敗の診断
  - Type: `model-invoked`
- **[`ast-grep-practice`](./engineering/ast-grep-practice/SKILL.md)** — ast-grep を project-local な構造 lint / rewrite として運用する。
  - Use when: 既存 linter で表現しにくい AST パターンの rule draft、rule-tests、sgconfig.yml、検証コマンド、kind 名・rule 例の確認
  - Type: `model-invoked`
- **[`tdd`](./engineering/tdd/SKILL.md)** — Red → Green → Refactor を public contract 単位で実行する。
  - Use when: 機能追加、バグ修正、仕様変更、リファクタリング、よほどの微修正ではないコード変更
  - Type: `model-invoked`
- **[`test-writing-style`](./engineering/test-writing-style/SKILL.md)** — テストを仕様として読める検証に整える。
  - Use when: テストの新規追加・修正・レビュー、命名・AAA・1テスト1関心・mock/fake の整理
  - Type: `model-invoked`

### Meta

- **[`apm-usage`](./meta/apm-usage/SKILL.md)** — APM で agent skill を管理・更新する手順を確認する。
  - Use when: apm.yml 更新、SHA pin 更新、global install / dotfiles 連携
  - Type: `model-invoked`
- **[`skill-workbench`](./meta/skill-workbench/SKILL.md)** — agent skill の作成・改善・レビュー・棚卸しを 1 つの lifecycle として扱う。
  - Use when: 新規 skill 作成、既存 skill 改善、skill diff / 全体レビュー、skill inventory audit
  - Type: `user-invoked`
- **[`retrospective-codify`](./meta/retrospective-codify/SKILL.md)** — 試行錯誤で得た再利用可能な知見を固定する。
  - Use when: 明示的な retrospective / codify 依頼、skill / AGENTS.md / ast-grep rule への知見固定
  - Type: `user-invoked`

### Personal

- **[`chouge-changelog`](./personal/chouge-changelog/SKILL.md)** — CHANGES.md が存在する repository で変更履歴を書く。
  - Use when: CHANGES.md 更新、release note 下書き、PR / commit 内容の変更履歴化
  - Type: `user-invoked`
- **[`chouge-git`](./personal/chouge-git/SKILL.md)** — chouge 個人の Git/GitHub 運用規約を適用する。
  - Use when: commit、branch、push、PR 作成・更新
  - Type: `model-invoked`

### Productivity

- **[`grilling`](./productivity/grilling/SKILL.md)** — 計画、設計、PRD、Design Doc、issue を一問ずつ詰める reusable discipline。
  - Use when: 他 skill から曖昧さ、未決定、依存する判断を一つずつ解消する
  - Type: `model-invoked`
- **[`grill-me`](./productivity/grill-me/SKILL.md)** — ユーザーが明示的に grill したい計画や設計を `grilling` session に渡す。
  - Use when: plan / design の stress-test、実装前の懸念洗い出し、判断分岐の解消
  - Type: `user-invoked`
- **[`handoff`](./productivity/handoff/SKILL.md)** — 現在の会話を別の agent が引き継げる handoff document に圧縮する。
  - Use when: セッション引き継ぎ、長い会話の圧縮、別 agent への作業移管
  - Type: `user-invoked`
- **[`herdr`](./productivity/herdr/SKILL.md)** — Herdr pane 内で workspace / tab / pane を操作する。
  - Use when: Herdr-managed pane で隣接 pane の出力確認、pane 分割、長時間 command / helper agent 起動、出力待ち
  - Type: `model-invoked`
- **[`teach`](./productivity/teach/SKILL.md)** — 現在のディレクトリを学習 workspace として使い、複数セッションで教える。
  - Use when: 新しい概念の学習、技術・技能の継続学習、学習記録の管理
  - Type: `user-invoked`
- **[`improve-agent-prompt`](./productivity/improve-agent-prompt/SKILL.md)** — agent-facing prompt を既存意図を保った最小差分で診断・改善する。
  - Use when: system prompt、agent instructions、tool description、AGENTS.md、skill、prompt stack の改善、明示された対象モデルへの prompt 適応
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

- **[`japanese-tech-writing`](./writing/japanese-tech-writing/SKILL.md)** — 日本語の技術文書・書籍原稿の文章規範。
  - Use when: 技術書・記事の執筆、草稿の推敲、日本語技術文書の構成レビュー
  - Type: `model-invoked`

## 運用

- dotfiles 側には global skill の install 一覧として `apm/apm.yml` だけを置く。
- skill 本体はこの repository を source of truth にする。
- dotfiles から参照するときは full SHA で pin する。
- skill 更新後に配布する場合は、`skill-workbench` の Review diff branch を通してから、この repository で commit / push し、dotfiles 側の SHA を更新する。
- commit / push / pin 更新 / `apm install -g` はユーザーが明示依頼した場合だけ行う。
