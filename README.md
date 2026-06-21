# nananaman/skills

nananaman の個人用 agent skills 集です。APM で配布・インストールする前提で管理します。

## Install

個別に入れる場合:

```sh
apm install -g nananaman/skills/meta/apm-usage#<full-sha>
apm install -g nananaman/skills/engineering/review-diff-code#<full-sha>
```

`apm.yml` で管理する場合:

```yaml
name: my-agent-context
version: 0.1.0
target: claude,agent-skills

dependencies:
  apm:
    - nananaman/skills/meta/apm-usage#<full-sha>
    - nananaman/skills/engineering/review-diff-code#<full-sha>
```

## Directory Policy

利用者が探しやすい用途別分類を主軸にします。

- `engineering/` — コード作業、設計、レビュー、デバッグなど。
- `sakura-cloud/` — さくらのクラウド関連サービスの作業ランブック。
- `personal/` — chouge 個人の運用デフォルトや作業規約。
- `productivity/` — 汎用的な作業フロー、思考補助、引き継ぎ、学習支援など。
- `writing/` — 文章執筆、編集、技術文書の推敲など。
- `meta/` — skill 管理、APM 運用、skill 作成など、このリポジトリや skill エコシステムを扱うもの。


## Skills

| Skill | Path | Description |
| --- | --- | --- |
| review-diff-code | `engineering/review-diff-code` | 現在の差分を厳しめにレビューする。 |
| create-pr | `engineering/create-pr` | 現在の branch からレビューしやすい GitHub draft PR を作成する。 |
| sakura-cloud-eventbus | `sakura-cloud/eventbus` | さくらのクラウド EventBus の実行設定、スケジュール、イベントトリガーを扱う。 |
| sakura-cloud-webaccel | `sakura-cloud/webaccel` | さくらのウェブアクセラレータのサイト追加、キャッシュ削除、SSL、オリジンガードを扱う。 |
| sakura-cloud-workflows | `sakura-cloud/workflows` | さくらのクラウド Workflows の YAML 作成、デバッグ、実行履歴確認を扱う。 |
| chouge-git | `personal/chouge-git` | chouge 個人の Git/GitHub 運用規約。 |
| chouge-changelog | `personal/chouge-changelog` | CHANGES.md が存在する repo で変更履歴を書く。 |
| apm-usage | `meta/apm-usage` | APM で agent skill を管理・更新する手順。 |
| create-skill | `meta/create-skill` | agent skill の作成・改善 draft を行う。 |
| reviewing-skills | `meta/reviewing-skills` | agent skill レビューの共通 rubric。 |
| review-diff-skill | `meta/review-diff-skill` | skill 変更 diff を commit / push / pin / install 前にレビューする。 |
| review-skill | `meta/review-skill` | skill 全体を棚卸しして課題を洗い出す。 |
| grill-me | `productivity/grill-me` | 計画や設計を着手前に容赦なく質問して詰める。 |
| teach | `productivity/teach` | 現在のディレクトリを学習 workspace として使い、複数セッションで教える。 |
| japanese-tech-writing | `writing/japanese-tech-writing` | 日本語の技術文書・書籍原稿の文章規範。 |

## 運用

- dotfiles 側には `apm/apm.yml` だけを残し、skill 本体はこのリポジトリを source of truth にする。
- dotfiles から参照するときは full SHA で pin する。
- skill 更新後に配布する場合は、`review-diff-skill` を通してから、このリポジトリで commit / push し、dotfiles 側の SHA を更新する。commit / push / pin 更新はユーザーが明示依頼した場合だけ行う。
