---
name: update-skills
description: グローバルまたはプロジェクト単位の APM skill 依存関係を最新化し、必要に応じて apm install を実行する。apm.yml の pin のずれ、ローカル参照先の同期漏れ、複数 skill の一括更新、正本のリポジトリと展開先の同期確認で使う。単一 skill の作成、本文編集、品質レビュー、通常の npm / Nix 依存更新では使わない。
disable-model-invocation: true
---

APM で管理している agent skill の依存関係を、正本と実際に使う manifest を取り違えずに最新へ更新する。
この skill は参照先の更新とインストールを運用する skill であり、skill 本文の編集や品質レビューは担当しない。

## 対象範囲

- 対象は APM の `dependencies.apm` にある skill の依存関係。
- グローバル skill の更新では、dotfiles の `apm/apm.yml` とユーザー単位の `~/.apm/apm.yml` の実体を確認する。
- プロジェクト単位の skill 更新では、対象リポジトリ直下の `apm.yml` を確認する。
- GitHub の依存関係は `owner/repo/path#full-sha` の pin を最新 commit SHA へ更新する。
- ローカルパスの依存関係は manifest を変えず、参照先 repository を最新化して展開へ反映する。
- skill 本文の作成・編集、差分レビュー、棚卸しは `skill-workbench` に委譲する。

## 安全上の制約

- 変更前に `git status --short` を確認し、既存の未コミット変更をユーザー所有として扱う。
- 既存変更があるファイルを変更する場合は、必ず差分の所有者と意図を確認する。
- `apm.lock.yaml` と `apm_modules/` は commit 対象にしない。
- ローカルパスの参照先 repository は、デフォルトブランチにいて working tree が clean かつ fast-forward できる場合だけ自律で最新化する。それ以外はユーザーの作業中とみなして更新せず、状態を報告して判断を待つ。
- update-skills は通常、参照先の更新からインストールまでを一組として扱う。ユーザーが「更新して」「グローバル」「プロジェクト単位」など更新を依頼した場合はインストールまで求めているものとして扱い、実行前に追加確認しない。
- インストールしないのは、ユーザーが「install はしない」「manifest だけ」「dry-run」などを明示した場合、またはレビューの指摘や取得失敗によって安全に進めない場合だけにする。
- `--update` 付き install は lock 内容の受け入れを伴うため、content hash mismatch が出た場合だけ、manifest が意図した full SHA を指していることを確認し、ユーザーが lock 更新を受け入れる判断をしてから提案または実行する。
- commit / push は、この skill の通常完了条件に含めない。ユーザーが明示した場合は `chouge-git` の規約に従う。

## 手順

1. 更新対象を決める。
   - ユーザーがパスを指定した場合はその `apm.yml` を対象にする。
   - グローバル更新の依頼なら、次を確認する。

```sh
readlink ~/.apm
realpath ~/.apm/apm.yml
git -C <dotfiles-repo> status --short
```

   - 現在のリポジトリに `apm.yml` があり、グローバル更新かプロジェクト単位の更新か曖昧な場合は確認する。

2. Manifest を読む。
   - `dependencies.apm` の各項目を列挙する。
   - 文字列形式と mapping 形式の依存関係を区別する。
   - GitHub、ローカルパス、pin なしの依存関係を分類する。
   - GitHub の依存関係に pin がない場合は、最新 full SHA で pin する変更案に含める。

3. 参照先の最新を取得する。
   - GitHub の依存関係 `owner/repo/path#old-sha` は、同じ `owner/repo` のデフォルトブランチの HEAD を取得する。

```sh
git ls-remote https://github.com/<owner>/<repo>.git HEAD
```

   - デフォルトブランチ以外を使う指示がある依存関係は、そのブランチまたは ref の SHA を取得する。
   - ローカルパスの依存関係は、参照先 repository ごとに fetch し、working tree の状態と upstream との差を確認する。

```sh
git -C <local-repo> fetch origin
git -C <local-repo> status --short
git -C <local-repo> rev-list --left-right --count HEAD...@{upstream}
```

   - 取得できない依存関係は更新せず、原因を報告に残す。

4. 更新計画を作る。
   - 依存関係ごとに変更前と変更後、変更有無、更新対象外理由を表にする。
   - 同一リポジトリの複数パスは同じ新しい commit に揃える。
   - 変更前と変更後が同じ依存関係は変更しない。
   - manifest の実体が symlink 経由の場合は、編集する実体パスを明記する。
   - インストールを実行する作業ディレクトリは、manifest があるリポジトリ直下として明記する。

5. 参照先を更新する。
   - GitHub の依存関係は manifest の full SHA だけを置換し、path / owner / repo / target は変えない。
   - `target: claude,agent-skills` など APM 0.14.2 の形式を勝手に変更しない。
   - 既存のコメント、並び順、空行をできるだけ保持する。
   - manifest を変更した場合は `git diff -- <manifest>` を確認する。
   - ローカルパスの依存関係は manifest を変えず、参照先 repository を fast-forward する。

```sh
git -C <local-repo> merge --ff-only <upstream>
```

6. 配布前レビューを行う。
   - skill の依存関係または APM manifest の変更は `skill-workbench` の差分レビューの対象として扱う。
   - 対応可能な指摘が残る場合はインストールへ進まない。
   - この skill 自身ではレビューの指摘を無視して進めない。

7. インストールする。
   - ユーザーが install 不要を明示していない限り、pin 更新後にインストールまで実行する。
   - グローバル更新なら次を使う。

```sh
apm install -g
```

   - プロジェクト単位の更新なら、対象リポジトリ直下で manifest の `target:` に従ってインストールする。ユーザーが対象の上書きを明示した場合だけ `--target` を付ける。

```sh
cd <repo-root> && apm install
cd <repo-root> && apm install --target <explicit-target>
```

   - content hash mismatch が出た場合は、manifest の SHA と意図を再確認し、ユーザーが lock 更新を受け入れる判断をしてから、同じ scope の install command に `--update` を付ける。

```sh
apm install -g --update
cd <repo-root> && apm install --update
cd <repo-root> && apm install --target <explicit-target> --update
```

   - ローカルパスを最新化した場合は、install の出力ではなく展開先のファイルで反映を確認する。

8. 結果を報告する。
   - 更新した manifest のパス。
   - 更新した依存関係と変更前後の commit。
   - 更新しなかった依存関係と理由。
   - インストールの実行有無と結果。
   - 残っている手動作業（レビュー、install、commit、push など）。

## 出力

```md
## Skill 更新の概要
- 対象 manifest: <パス>
- 対象範囲: グローバル / プロジェクト単位
- Manifest の実体パス: <パス、または該当なし>
- 既存の未コミットファイル: <なし、または概要>

## 依存関係の更新
| 依存関係 | 変更前 | 変更後 | 対応 |
|---|---|---|---|
| `<owner/repo/path>` | `<変更前の SHA>` | `<変更後の SHA>` | pin 更新 / 変更なし / 対象外 |
| `<local path>` | `<変更前の commit>` | `<変更後の commit>` | 最新化 / 変更なし / 保留 |

## 更新しなかった項目
- `<依存関係>`: <理由>

## レビューとインストール
- skill-workbench の差分レビュー: 合格 / 指摘あり / 未実行（<理由>）
- install: 実行 / 未実行（<理由>）
- コマンド: `<コマンド、または該当なし>`

## 残る作業
1. <必要なら commit / push / install など>
```

## 完了条件

- 対象 manifest と実体パスを確認した。
- APM の依存関係を参照方式ごとに分類した。
- GitHub の依存関係は最新 full SHA を取得し、変更する場合は manifest の SHA pin だけを更新して diff を確認した。
- ローカルパスの依存関係は参照先 repository の同期状態を確認し、最新化したか、更新しない理由を示した。
- `skill-workbench` の差分レビューを通すか、未実行理由を明示した。
- インストールの実行有無と次の対応を報告した。
