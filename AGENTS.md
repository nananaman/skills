# AGENTS.md

このリポジトリは nananaman の個人用 agent skills の source of truth です。

## 方針

- `SKILL.md` は日本語で書いてよい。
- 各 skill は APM から `nananaman/skills/<path>#<full-sha>` で参照できる形にする。
- skill ディレクトリ名は `SKILL.md` frontmatter の `name:` と一致させる。
- セキュリティ上公開できない内容はこのリポジトリに置かない。

## 更新手順

1. skill を編集する。
2. commit / push する。
3. commit SHA を取得する。
4. dotfiles の `apm/apm.yml` の参照 SHA を更新する。
5. `apm install -g` で展開する。
