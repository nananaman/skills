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
- install、manifest 更新、lock 更新、APM pin 更新、展開は、ユーザーが明示依頼した場合だけ実行する。依頼がない場合はコマンド提示に留める。

## global skill と project-local skill

APM では、常時有効にする global skill と、特定 repo でだけ使う project-local skill を分けて管理する。

| 用途 | manifest | install | 展開先 |
|---|---|---|---|
| 全 repo で常時使う skill | dotfiles の `apm/apm.yml` | `apm install -g` | `~/.claude/skills`, `~/.agents/skills` |
| 特定 repo でだけ使う skill | repo root の `apm.yml` | `apm install --target claude,agent-skills` | `<repo>/.claude/skills`, `<repo>/.agents/skills` |

## User-scope manifest path

`apm install -g` は current directory の `apm/apm.yml` ではなく、user-scope の `~/.apm/apm.yml` を読む。
dotfiles では `~/.apm` が repo の `apm/` へ symlink されるため、worktree で作業している場合は更新先を間違えやすい。

pin 更新や global install の前に、必ず実体を確認する。

```sh
readlink ~/.apm
realpath ~/.apm/apm.yml
grep -n "<skill-name>" ~/.apm/apm.yml
```

`~/.apm` が本体 repo を指している場合、worktree 側の `apm/apm.yml` だけを更新しても `apm install -g` には反映されない。
その場合は `~/.apm/apm.yml` の実体側を更新するか、どの manifest を source of truth として変更するかをユーザーに確認する。

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
2. `apm/apm.yml` の `dependencies.apm` 変更案を作る。
3. `review-diff-skill` で APM manifest / pin 変更をレビューする。
4. actionable finding がなく、ユーザーが明示依頼した場合だけ `apm/apm.yml` を更新する。
5. ユーザーが明示依頼した場合だけインストールする。

```sh
apm install -g
```

## 自作 skill の更新

1. `nananaman/skills` で skill を編集する。
2. `review-diff-skill` で差分レビューする。
3. actionable finding がなく、ユーザーが明示依頼した場合だけ commit / push する。
4. full SHA を取得する。

```sh
git rev-parse HEAD
```

5. `readlink ~/.apm` と `realpath ~/.apm/apm.yml` で user-scope manifest の実体を確認する。
6. `grep -n "<skill-name>" ~/.apm/apm.yml` で、`apm install -g` が読む pin を確認する。
7. ユーザーが明示依頼した場合だけ、`~/.apm/apm.yml` の実体、または dotfiles の source-of-truth manifest の該当 SHA を更新する。
8. ユーザーが明示依頼した場合だけ展開する。

```sh
apm install -g
```

pin 更新後に content hash mismatch が出た場合は、まず `readlink ~/.apm`、`realpath ~/.apm/apm.yml`、該当 pin を再確認する。manifest が意図した full SHA を指しており、変更を受け入れる判断ができる場合だけ、lock 更新として `apm install -g --update` を実行する。`apm.lock.yaml` と `apm_modules/` は user-scope の cache / lock として扱い、dotfiles へ commit しない。

## project-local skill の導入

特定 repo の作業でだけ使う skill は、repo root の `apm.yml` で管理する。
GitHub 上の skill は、`fetch_content` や手動コピーではなく APM で導入する。
導入前に `review-diff-skill` で APM manifest / pin / install 対象をレビューし、actionable finding が残る場合は進まない。
ユーザーが明示依頼した場合だけ、次のような install command を実行する。

```sh
apm install <owner/repo/path#full-sha> --target claude,agent-skills
```

例：skill 作成・レビュー一式を導入する。

```sh
apm install \
  nananaman/skills/meta/create-skill#<full-sha> \
  nananaman/skills/meta/reviewing-skills#<full-sha> \
  nananaman/skills/meta/review-diff-skill#<full-sha> \
  nananaman/skills/meta/review-skill#<full-sha> \
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
