# nananaman/skills

nananaman の個人用 agent skills 集です。APM で配布・インストールする前提で管理します。

## Install

個別に入れる場合:

```sh
apm install -g nananaman/skills/meta/apm-usage#<full-sha>
apm install -g nananaman/skills/engineering/code-review#<full-sha>
```

`apm.yml` で管理する場合:

```yaml
name: my-agent-context
version: 0.1.0
target: claude,agent-skills

dependencies:
  apm:
    - nananaman/skills/meta/apm-usage#<full-sha>
    - nananaman/skills/engineering/code-review#<full-sha>
```

## Directory Policy

利用者が探しやすい用途別分類を主軸にします。

- `engineering/` — コード作業、設計、レビュー、デバッグなど。
- `productivity/` — 汎用的な作業フロー、思考補助、引き継ぎ、学習支援など。
- `writing/` — 文章執筆、編集、技術文書の推敲など。
- `meta/` — skill 管理、APM 運用、skill 作成など、このリポジトリや skill エコシステムを扱うもの。


## Skills

| Skill | Path | Description |
| --- | --- | --- |
| code-review | `engineering/code-review` | 軽量モデル優先の厳しめコードレビュー支援。 |
| apm-usage | `meta/apm-usage` | APM で agent skill を管理・更新する手順。 |
| skill-creator | `meta/skill-creator` | agent skill の作成・改善・評価と品質基準。 |
| grill-me | `productivity/grill-me` | 計画や設計を着手前に容赦なく質問して詰める。 |
| japanese-tech-writing | `writing/japanese-tech-writing` | 日本語の技術文書・書籍原稿の文章規範。 |

## 運用

- dotfiles 側には `apm/apm.yml` だけを残し、skill 本体はこのリポジトリを source of truth にする。
- dotfiles から参照するときは full SHA で pin する。
- skill 更新後は、このリポジトリで commit / push してから dotfiles 側の SHA を更新する。
