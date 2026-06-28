---
name: update-skills
description: global / project-local APM skill dependencies を最新の full SHA へ更新し、必要に応じて apm install を実行する。apm.yml の pin drift、複数 skill の一括更新、source-of-truth repo と展開先の同期確認で使う。単一 skill の作成・本文編集・品質レビュー・通常の npm / Nix 依存更新では使わない。
disable-model-invocation: true
---

APM で管理している agent skill dependency を、source-of-truth と実利用 manifest を取り違えずに最新へ更新する。
この skill は pin 更新と install の運用 skill であり、skill 本文の編集や品質レビューは担当しない。

## Scope

- 対象は APM の `dependencies.apm` にある skill dependency。
- global skill 更新では、dotfiles の `apm/apm.yml` と user-scope の `~/.apm/apm.yml` の実体を確認する。
- project-local skill 更新では、対象 repo root の `apm.yml` を確認する。
- GitHub dependency は `owner/repo/path#full-sha` の pin を最新 commit SHA へ更新する。
- local path dependency は更新対象外として記録する。
- skill 本文の作成・編集は `create-skill`、差分レビューは `review-diff-skill`、棚卸しは `audit-skills` に委譲する。

## Safety Rules

- 変更前に `git status --short` を確認し、既存の未コミット変更を user-owned として扱う。
- 既存変更があるファイルを変更する場合は、必ず差分の所有者と意図を確認する。
- `apm.lock.yaml` と `apm_modules/` は commit 対象にしない。
- update-skills は通常、pin 更新から install までを 1 セットとして扱う。ユーザーが「更新して」「global」「project-local」など更新依頼をした場合は install まで求めているものとして扱い、install 実行前に追加確認しない。
- install を実行しないのは、ユーザーが「install はしない」「manifest だけ」「dry-run」などを明示した場合、またはレビュー finding / 取得失敗などで安全に進めない場合だけにする。
- `--update` 付き install は lock 内容の受け入れを伴うため、content hash mismatch が出た場合だけ、manifest が意図した full SHA を指していることを確認し、ユーザーが lock 更新を受け入れる判断をしてから提案または実行する。
- commit / push は、この skill の通常完了条件に含めない。ユーザーが明示した場合は `chouge-git` の規約に従う。

## Workflow

1. 更新対象を決める。
   - ユーザーが path を指定した場合はその `apm.yml` を対象にする。
   - global 更新の依頼なら、次を確認する。

```sh
readlink ~/.apm
realpath ~/.apm/apm.yml
git -C <dotfiles-repo> status --short
```

   - 現在の repo に `apm.yml` があり、global か project-local か曖昧な場合は確認する。

2. manifest を読む。
   - `dependencies.apm` の各 entry を列挙する。
   - 文字列 dependency と mapping dependency を区別する。
   - GitHub dependency、local path dependency、pin なし dependency を分類する。
   - pin なし dependency がある場合は、最新 full SHA で pin する変更案に含める。

3. 最新 SHA を取得する。
   - GitHub dependency `owner/repo/path#old-sha` は、同じ `owner/repo` の default branch HEAD を取得する。

```sh
git ls-remote https://github.com/<owner>/<repo>.git HEAD
```

   - default branch 以外を使う指示がある dependency は、その branch / ref の SHA を取得する。
   - 取得できない dependency は更新せず、原因を report に残す。

4. 更新計画を作る。
   - dependency ごとに `old -> new`、変更有無、更新対象外理由を表にする。
   - 同一 repo の複数 path は同じ new SHA に揃える。
   - old と new が同じ dependency は変更しない。
   - manifest 実体が symlink 経由の場合は、編集する実体 path を明記する。
   - install を実行する working directory は、manifest がある repo root として明記する。

5. manifest を更新する。
   - full SHA だけを置換し、path / owner / repo / target は変えない。
   - `target: claude,agent-skills` など APM 0.14.2 の形式を勝手に変更しない。
   - 既存のコメント、並び順、空行をできるだけ保持する。
   - 変更後に `git diff -- <manifest>` を確認する。

6. 配布前レビューを行う。
   - skill dependency / APM manifest の変更は `review-diff-skill` の対象として扱う。
   - actionable finding が残る場合は install へ進まない。
   - この skill 自身では review finding を無視して進めない。

7. install する。
   - ユーザーが install 不要を明示していない限り、pin 更新後に install まで実行する。
   - global 更新なら次を使う。

```sh
apm install -g
```

   - project-local 更新なら、対象 repo root で manifest の `target:` に従って install する。ユーザーが target override を明示した場合だけ `--target` を付ける。

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

8. 結果を報告する。
   - 更新した manifest path。
   - 更新した dependency と `old -> new`。
   - 更新しなかった dependency と理由。
   - install 実行有無と結果。
   - 残っている手動作業（review、install、commit、push など）。

## Output

```md
## Skill Update Summary
- Target manifest: <path>
- Scope: global / project-local
- Manifest realpath: <path or n/a>
- Existing dirty files: <none or summary>

## Dependency Updates
| Dependency | Old SHA | New SHA | Action |
|---|---|---|---|
| `<owner/repo/path>` | `<old>` | `<new>` | updated / unchanged / skipped |

## Skipped
- `<dependency>`: <reason>

## Review / Install
- review-diff-skill: passed / findings / not run (<reason>)
- install: run / not run (<reason>)
- command: `<command or n/a>`

## Next Steps
1. <必要なら commit / push / install など>
```

## Done Criteria

- 対象 manifest と実体 path を確認した。
- APM dependency を分類し、更新対象と対象外を分けた。
- GitHub dependency の最新 full SHA を取得した。
- 変更する場合は SHA pin だけを更新し、diff を確認した。
- `review-diff-skill` の gate を通すか、未実行理由を明示した。
- install 実行有無と次アクションを報告した。
