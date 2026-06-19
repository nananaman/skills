---
name: apm-usage
description: APM で agent skill を管理・更新するときに使う。apm.yml、SHA pin、global install、dotfiles 連携の手順を確認する。
---

# APM Usage

APM で agent skill を管理・更新するときの運用手順です。

## 基本方針

- グローバルに入れる skill 一覧は dotfiles の `apm/apm.yml` で管理する。
- 自作 reusable skill 本体は `nananaman/skills` を source of truth にする。
- 外部 repo / 自作 repo の skill は full SHA で pin する。
- global skill 管理では、`apm.lock.yaml` と `apm_modules/` は commit しない。
- project 固有 skill は、その project 配下に置く。汎用化できるものだけ `nananaman/skills` に移す。

## global skill と project-local skill

APM では、常時有効にする global skill と、特定 repo でだけ使う project-local skill を分けて管理する。

| 用途 | manifest | install | 展開先 |
|---|---|---|---|
| 全 repo で常時使う skill | dotfiles の `apm/apm.yml` | `apm install -g` | `~/.claude/skills`, `~/.agents/skills` |
| 特定 repo でだけ使う skill | repo root の `apm.yml` | `apm install --target claude,agent-skills` | `<repo>/.claude/skills`, `<repo>/.agents/skills` |

## `apm.yml` の基本形

APM 0.14.2 の user scope では `targets:` ではなく `target:` を使う。

```yaml
name: chouge-agent-context
version: 0.1.0
target: claude,agent-skills

dependencies:
  apm:
    - nananaman/skills/meta/apm-usage#<full-sha>
```

## skill の追加

1. 追加したい skill の repo / path / commit SHA を確認する。
2. `apm/apm.yml` の `dependencies.apm` に追加する。
3. インストールする。

```sh
apm install -g
```

## 自作 skill の更新

1. `nananaman/skills` で skill を編集する。
2. commit / push する。
3. full SHA を取得する。

```sh
git rev-parse HEAD
```

4. dotfiles の `apm/apm.yml` の該当 SHA を更新する。
5. 展開する。

```sh
apm install -g
```

## project-local skill の導入

特定 repo の作業でだけ使う skill は、repo root の `apm.yml` で管理する。
GitHub 上の skill は、`fetch_content` や手動コピーではなく APM で導入する。

```sh
apm install <owner/repo/path#full-sha> --target claude,agent-skills
```

例：

```sh
apm install \
  anthropics/skills/skills/skill-creator#<full-sha> \
  --target claude,agent-skills
```

このコマンドは repo root の `apm.yml` と `apm.lock.yaml` を更新し、`.claude/skills/` と `.agents/skills/` に skill を展開する。

## local path skill と GitHub skill の使い分け

### local path skill

一時的な検証だけに使う。

```yaml
dependencies:
  apm:
    - path: ./skills/example
```

### GitHub skill

継続運用する skill は GitHub 参照にする。

```yaml
dependencies:
  apm:
    - nananaman/skills/meta/example#<full-sha>
```

## dotfiles の manifest

dotfiles repo では、二つの APM manifest を区別する。

- `apm/apm.yml`：user-scope の global skill を管理する。
- repo root の `apm.yml`：dotfiles repo 自体で使う project-local skill を管理する。

## global skill で dotfiles 側に残すもの

```text
apm/apm.yml
apm/.gitignore
```

global skill 本体は dotfiles に置かない。

## 確認コマンド

```sh
apm install -g
ls ~/.claude/skills
ls ~/.agents/skills
```
