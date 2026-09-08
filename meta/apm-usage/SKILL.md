---
name: apm-usage
description: APM で agent skill を管理または更新するときに使う。apm.yml、参照方式（path / SHA pin）、グローバルインストール、dotfiles 連携の手順を確認する。
---

# APM の運用

APM の manifest、参照方式、展開先を確認するときに使う。
依存関係の最新化は [update-skills](../update-skills/SKILL.md)、skill 本文の編集は `implement` と `skill-workbench` が担当する。

## 正本と scope

- 再利用可能な自作 skill 本体は `nananaman/skills` を正本とする。project 固有 skill はその project に置く。
- グローバルの依存一覧は dotfiles の `apm/apm.yml`。グローバルの `apm.lock.yaml` と `apm_modules/` は commit しない。
- 正本 repository をローカルに置く場合は path 参照、置かない場合は full SHA pin を使う。

| scope | manifest | install | 展開先 |
|---|---|---|---|
| グローバル | `~/.apm/apm.yml`（dotfiles の `apm/apm.yml` へのリンク） | `apm install -g` | `~/.claude/skills`, `~/.agents/skills` |
| project | repository 直下の `apm.yml` | repository 直下で `apm install` | `.claude/skills`, `.agents/skills` |

既存 manifest の形式と target を維持し、形式やオプションが不明ならインストール済みの `apm install --help` で確認する。
project の target 上書きは依頼がある場合にだけ行う。

## user-scope の実体確認

グローバルの manifest 更新・install 前に `realpath ~/.apm/apm.yml` で実体を確認する。
worktree の `apm/apm.yml` と install が読む実体が異なる場合、worktree の編集だけでは反映されない。
依頼された正本と install の入力を照合し、別 checkout を無断で編集しない。どちらを変更するか会話から決められなければ確認する。

## 参照方式

```yaml
dependencies:
  apm:
    - path: ~/ghq/github.com/nananaman/skills/meta/example
    - path: ./skills/example
    - owner/repo/path#<full-sha>
```

path 参照は manifest を変えず、参照先 repository の更新で追従する。
SHA pin は参照先の full SHA を manifest に記録して固定する。
GitHub 上の skill は手動コピーではなく APM で導入する。

## 変更と展開

ユーザーが依頼した範囲で manifest・参照先を更新する。同じ対象・操作への許可は引き継ぐ。
提案だけの依頼では変更せず、本文編集だけの依頼から install や依存更新を推測しない。
依存関係の「更新」は通常 install まで含む。manifest のみ、dry-run、install 不要という指定は優先する。
commit / push は別途明示依頼がある場合だけ行う。

追加・更新した manifest の参照先、SHA、scope、target を実際の差分で確認する。
レビューの規模は `skill-workbench` の変更リスクに合わせ、依存更新だけで全 skill 本文の再監査を必須にしない。
install 後は展開先を確認する。特に path 参照はコマンドの成功表示だけで反映済みと判断しない。

content hash mismatch が出たら manifest の実体と意図した SHA を再確認する。
`--update` は lock 内容の受け入れを伴うため、変更内容を説明し、ユーザーが受け入れた場合だけ同じ scope の install に付ける。既に当該変更への受け入れがあれば再確認しない。
