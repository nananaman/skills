---
name: apm-usage
description: APM で agent skill を管理または更新するときに使う。apm.yml、参照方式（path / SHA pin）、グローバルインストール、dotfiles 連携の手順を確認する。
---

# APM の運用

APM で agent skill を管理・更新するときの運用手順です。

## 基本方針

- グローバルに入れる skill 一覧は dotfiles の `apm/apm.yml` で管理する。
- 自作した再利用可能な skill 本体は `nananaman/skills` を正本にする。
- 正本をローカルに置く skill は path で参照し、参照先 repository の最新化で追従する。ローカルに置かない skill は full SHA で pin する。
- グローバル skill の管理では、`apm.lock.yaml` と `apm_modules/` は commit しない。
- project 固有 skill は、その project 配下に置く。汎用化できるものだけ `nananaman/skills` に移す。
- install、manifest 更新、lock 更新、APM pin 更新、展開は、ユーザーが明示依頼した場合だけ実行する。依頼がない場合はコマンド提示に留める。

## グローバル skill とプロジェクト単位の skill

APM では、常時有効にするグローバル skill と、特定リポジトリでだけ使うプロジェクト単位の skill を分けて管理する。

| 用途 | manifest | install | 展開先 |
|---|---|---|---|
| 全 repo で常時使う skill | dotfiles の `apm/apm.yml` | `apm install -g` | `~/.claude/skills`, `~/.agents/skills` |
| 特定リポジトリでだけ使う skill | リポジトリ直下の `apm.yml` | `apm install --target claude,agent-skills` | `<repo>/.claude/skills`, `<repo>/.agents/skills` |

## ユーザー単位の manifest の場所

`apm install -g` は current directory の `apm/apm.yml` ではなく、user-scope の `~/.apm/apm.yml` を読む。
dotfiles では `~/.apm` が repo の `apm/` へ symlink されるため、worktree で作業している場合は更新先を間違えやすい。

pin の更新やグローバルインストールの前に、必ず実体を確認する。

```sh
readlink ~/.apm
realpath ~/.apm/apm.yml
grep -n "<skill-name>" ~/.apm/apm.yml
```

`~/.apm` が本体 repo を指している場合、worktree 側の `apm/apm.yml` だけを更新しても `apm install -g` には反映されない。
その場合は `~/.apm/apm.yml` の実体側を更新するか、どの manifest を正本として変更するかをユーザーに確認する。

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

1. 追加したい skill のリポジトリ、パス、参照方式（path または full SHA）を確認する。
2. `apm/apm.yml` の `dependencies.apm` 変更案を作る。
3. `skill-workbench` の差分レビューで APM manifest の変更をレビューする。
4. 対応可能な指摘がなく、ユーザーが明示依頼した場合だけ `apm/apm.yml` を更新する。
5. ユーザーが明示依頼した場合だけインストールする。

```sh
apm install -g
```

## 自作 skill の更新

1. `nananaman/skills` で skill を編集する。
2. `skill-workbench` の差分レビューを実行する。
3. 対応可能な指摘がなく、ユーザーが明示依頼した場合だけ commit / push する。
4. `readlink ~/.apm` と `realpath ~/.apm/apm.yml` で user-scope manifest の実体を確認する。
5. `grep -n "<skill-name>" ~/.apm/apm.yml` で、`apm install -g` が読む参照方式を確認する。
6. ユーザーが明示依頼した場合だけ参照先を更新する。path 参照なら manifest を変えずに参照先 repository を最新化し、pin なら `git rev-parse HEAD` の full SHA へ `~/.apm/apm.yml` の実体、または dotfiles の source-of-truth manifest を更新する。
7. ユーザーが明示依頼した場合だけ展開する。

```sh
apm install -g
```

pin 更新後に content hash mismatch が出た場合は、まず `readlink ~/.apm`、`realpath ~/.apm/apm.yml`、該当 pin を再確認する。manifest が意図した full SHA を指しており、変更を受け入れる判断ができる場合だけ、lock 更新として `apm install -g --update` を実行する。`apm.lock.yaml` と `apm_modules/` は user-scope の cache / lock として扱い、dotfiles へ commit しない。

## プロジェクト単位の skill の導入

特定リポジトリの作業でだけ使う skill は、リポジトリ直下の `apm.yml` で管理する。
GitHub 上の skill は、`fetch_content` や手動コピーではなく APM で導入する。
導入前に `skill-workbench` の差分レビューで APM manifest、pin、インストール対象を確認し、対応可能な指摘が残る場合は進まない。
ユーザーが明示依頼した場合だけ、次のような install command を実行する。

```sh
apm install <owner/repo/path#full-sha> --target claude,agent-skills
```

例：skill 作成・レビュー一式を導入する。

```sh
apm install \
  nananaman/skills/meta/skill-workbench#<full-sha> \
  --target claude,agent-skills
```

このコマンドはリポジトリ直下の `apm.yml` と `apm.lock.yaml` を更新し、`.claude/skills/` と `.agents/skills/` に skill を展開する。

## local path skill と GitHub skill の使い分け

### local path skill

正本 repository をローカルに置き、pin なしで最新へ追従する場合に使う。
更新は manifest ではなく参照先 repository の最新化で行い、手順は `../update-skills/SKILL.md` に従う。

```yaml
dependencies:
  apm:
    - path: ~/ghq/github.com/nananaman/skills/meta/example
    - path: ./skills/example
```

### GitHub skill

正本をローカルに置かない場合、または環境をまたいで同じ内容へ固定する場合に使う。

```yaml
dependencies:
  apm:
    - nananaman/skills/meta/example#<full-sha>
```

## dotfiles の manifest

dotfiles repo では、二つの APM manifest を区別する。

- `apm/apm.yml`：ユーザー単位のグローバル skill を管理する。
- リポジトリ直下の `apm.yml`：dotfiles リポジトリ自体で使うプロジェクト単位の skill を管理する。

## グローバル skill で dotfiles 側に残すもの

```text
apm/apm.yml
apm/.gitignore
```

グローバル skill 本体は dotfiles に置かない。

## 確認コマンド

```sh
apm install -g
ls ~/.claude/skills
ls ~/.agents/skills
```
