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
- `apm.lock.yaml` と `apm_modules/` は commit しない。
- project 固有 skill は、その project 配下に置く。汎用化できるものだけ `nananaman/skills` に移す。

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

## dotfiles 側に残すもの

```text
apm/apm.yml
apm/.gitignore
```

skill 本体は dotfiles に置かない。

## 確認コマンド

```sh
apm install -g
ls ~/.claude/skills
ls ~/.agents/skills
```
