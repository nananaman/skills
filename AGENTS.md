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
- `productivity/`: 汎用的な作業フロー、思考補助、引き継ぎ、学習支援など。
- `writing/`: 文章執筆、編集、技術文書の推敲など。
- `meta/`: skill 管理、APM 運用、skill 作成など、このリポジトリや skill エコシステムを扱うもの。

今は `skills/` ルート、カテゴリ別 `README.md`、`in-progress/`、`deprecated/` は作らない。実験中・廃止予定の skill はトップレベル `README.md` または各 skill 本文で注記する。

## 更新手順

1. skill を編集する。
2. commit / push する。
3. commit SHA を取得する。
4. dotfiles の `apm/apm.yml` の参照 SHA を更新する。
5. `apm install -g` で展開する。
