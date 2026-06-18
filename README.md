# nananaman/skills

nananaman の個人用 agent skills 集です。APM で配布・インストールする前提で管理します。

## Install

個別に入れる場合:

```sh
apm install -g nananaman/skills/meta/apm-usage#<full-sha>
apm install -g nananaman/skills/meta/code-review#<full-sha>
```

`apm.yml` で管理する場合:

```yaml
name: my-agent-context
version: 0.1.0
target: claude,agent-skills

dependencies:
  apm:
    - nananaman/skills/meta/apm-usage#<full-sha>
    - nananaman/skills/meta/code-review#<full-sha>
```

## Skills

| Skill | Path | Description |
| --- | --- | --- |
| apm-usage | `meta/apm-usage` | APM で agent skill を管理・更新する手順。 |
| code-review | `meta/code-review` | 軽量モデル優先の厳しめコードレビュー支援。 |

## 運用

- dotfiles 側には `apm/apm.yml` だけを残し、skill 本体はこのリポジトリを source of truth にする。
- dotfiles から参照するときは full SHA で pin する。
- skill 更新後は、このリポジトリで commit / push してから dotfiles 側の SHA を更新する。
