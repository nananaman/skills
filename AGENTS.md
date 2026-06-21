# AGENTS.md

このリポジトリは nananaman の個人用 agent skills の source of truth です。

## 方針

- `SKILL.md` は日本語で書いてよい。
- 各 skill は APM から `nananaman/skills/<path>#<full-sha>` で参照できる形にする。
- skill ディレクトリ名は `SKILL.md` frontmatter の `name:` と一致させる。
- セキュリティ上公開できない内容はこのリポジトリに置かない。

## ディレクトリ分類

利用者が探しやすい用途別分類を主軸にする。

- `engineering/`: コード作業、設計、レビュー、デバッグなど。
- `sakura-cloud/`: さくらのクラウド関連サービスの作業ランブック。
- `personal/`: chouge 個人の運用デフォルトや作業規約。
- `productivity/`: 汎用的な作業フロー、思考補助、引き継ぎ、学習支援など。
- `writing/`: 文章執筆、編集、技術文書の推敲など。
- `meta/`: skill 管理、APM 運用、skill 作成など、このリポジトリや skill エコシステムを扱うもの。

## skill 名

通常は skill ディレクトリ名と `SKILL.md` frontmatter の `name:` を一致させる。
provider や product で namespace を切る場合、leaf directory は短いサービス名にしてよい。
その場合でも `name:` は衝突を避けるため `provider-service` 形式にする。

例: `sakura-cloud/eventbus` + `name: sakura-cloud-eventbus`


## 更新手順

1. skill を編集する。
2. `review-diff-skill` で差分レビューする。
3. actionable finding がなく、ユーザーが明示依頼した場合だけ commit / push する。
4. commit SHA を取得する。
5. ユーザーが明示依頼した場合だけ、dotfiles の `apm/apm.yml` の参照 SHA を更新する。
6. ユーザーが明示依頼した場合だけ、`apm install -g` で展開する。
