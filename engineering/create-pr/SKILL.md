---
name: create-pr
description: 現在の branch から GitHub PR を作成する。通常は draft にし、ready PR はユーザー明示指示時だけ許可する。PR template、diff、commit、テスト状況を整理する。
---

# Create PR

現在の branch から、reviewer がすぐ読める GitHub PR を作成する。通常は draft PR にし、ready PR はユーザーが明示的に指示した場合だけ許可する。既存 PR がある場合は重複作成せず、更新または中止を提案する。

## 原則

- PR 方針は `chouge-git` の Pull Request 節に従う。
- 作成する PR は通常 draft にする。ready PR で作成するのは、ユーザーが明示的に ready PR 作成を指示した場合だけにする。
- project 規則が ready PR 作成を求めていても、ユーザーの明示指示がなければ draft で作成する。
- project に PR template がある場合は、その構成を優先して body を作る。
- PR body は実際の diff、commit、テスト状況、review gate の結果と一致させる。
- uncommitted changes、未 push、base branch 不明、既存 PR などの状態を確認してから作成する。
- push または PR 作成の前に、変更種別に応じた review gate が通っていることを確認する。
- history rewrite、force push、commit 整理はこの skill の責務外。必要なら別作業として提案する。

## Workflow

1. 現在の repository 状態を確認する。

   ```bash
   git status --short
   git branch --show-current
   git remote -v
   gh repo view --json nameWithOwner,defaultBranchRef
   ```

2. base branch を決める。
   - 既存 PR がある場合は `gh pr view --json baseRefName,headRefName,url,state,isDraft,title,body` を見る。
   - 既存 PR がなければ GitHub default branch を使う。
   - ユーザーが base を指定している場合はそれを優先する。

3. branch の差分を読む。

   ```bash
   git fetch origin <base>
   git log --oneline --decorate origin/<base>..HEAD
   git diff --stat origin/<base>...HEAD
   git diff --name-status origin/<base>...HEAD
   ```

   `origin/<base>...HEAD` が今回の目的だけを含むことを確認する。既に merge 済みの commit、別目的の変更、古い base 由来の差分が混ざる場合は、PR 作成へ進まず、最新 base へ載せ替える案または branch 分割案を提示してユーザーに確認する。history rewrite が必要なら `chouge-git` の History Rewrite に委譲し、共有済み branch では `--force-with-lease` を使う前に明示確認を取る。

4. PR template を探す。

   優先順は GitHub の慣習に合わせる。

   ```text
   .github/pull_request_template.md
   .github/PULL_REQUEST_TEMPLATE.md
   .github/PULL_REQUEST_TEMPLATE/*.md
   docs/pull_request_template.md
   docs/PULL_REQUEST_TEMPLATE.md
   pull_request_template.md
   PULL_REQUEST_TEMPLATE.md
   ```

   複数 template がある場合は、変更内容に最も近いものを選ぶ。判断できなければ候補を示してユーザーに確認する。

5. 必要に応じて変更内容を読む。
   - PR body に書く必要がある主要ファイルを読む。
   - generated file、lockfile、機械的変更、テストだけの変更は分類して明示する。
   - PR body で local markdown issue / Design Doc / changelog などの repository 内 artifact を参照する場合は、その artifact が base branch に既に存在するか、今回の branch diff に含まれているかを確認する。存在しない artifact を参照する PR body は作らない。
   - 大きすぎる PR なら、PR 作成前に split を提案する。

6. PR title / body の下書きを作る。
   - template がある場合は見出しや checklist を保ち、空欄を実 diff に基づいて埋める。
   - template がない場合は次の構成を使う。

   ```md
   ## Summary
   - 

   ## Changes
   - 

   ## Tests
   - 

   ## Review notes
   - 
   ```

   `Tests` には、実行したコマンドを書く。未実行なら `未実行` と理由を書く。推測で「テスト済み」と書かない。
   `Review notes` には、後続の review gate 確認後に、review gate の種類、実行した skill / command、対象 base、結果を書く。review gate が不要な docs-only 変更なら、その理由を書く。

7. review gate を確認する。
   - docs-only の変更なら review gate は不要。
   - skill 変更を含むなら `skill-workbench` の Review diff branch を使い、対象 diff と結果を記録する。
   - code / config / test / CI / runtime behavior に影響する変更を含むなら `review-diff-code` を使う。既定は `~/.agents/skills/review-diff-code/scripts/review-diff-code.py --mode branch --base origin/<base>`。dirty worktree を含める必要がある場合は `--mode local` を使う。
   - 既に同じ base / head diff に対して review 済みなら再実行しなくてよい。
   - 会話、直近の作業ログ、PR body の `Review notes` などで review 済みと確認できなければ、未実施として扱う。
   - 未実施なら push 前に実行する。push が不要な場合でも、PR 作成前に実行する。
   - actionable finding が残る場合は、push / PR 作成へ進まない。
   - review gate の実行または確認後、PR body の `Review notes` を結果に合わせて更新する。

8. PR を作成する。
   - 既存 PR がない場合だけ作成する。
   - body は一時ファイルに書き出し、`--body-file` を使う。
   - head branch が remote にない場合は push する。push 前に remote と branch 名を確認する。
   - ユーザーが明示的に ready PR 作成を指示していない場合は `--draft` を付ける。

   ```bash
   gh pr create \
     --draft \
     --base <base> \
     --head <branch> \
     --title "<title>" \
     --body-file <body-file>
   ```

   ユーザーが明示的に ready PR 作成を指示した場合だけ、`--draft` を外してよい。

9. 作成後に URL と reviewer 向け要点を報告する。

## Existing PR Handling

同じ branch に既存 PR がある場合は、重複作成しない。

```bash
gh pr view --json url,state,isDraft,title,body,baseRefName,headRefName
```

- 既存 PR が draft なら、必要に応じて `gh pr edit --title ... --body-file ...` で更新する。
- 既存 PR が ready for review なら、draft に戻せない前提で扱い、更新してよいか確認する。
- closed PR しかない場合は、新規作成してよいか確認する。

## Template Handling

template を使うときは、次を守る。

- checklist を削除しない。該当しない項目は未チェックのまま理由を書く。
- issue link、screenshot、migration、rollout など project 固有の欄を勝手に省略しない。
- template の文言と矛盾する内容を書かない。
- template の要求情報が diff から分からない場合は、PR 作成前にユーザーへ質問する。

## Safety Checks

次の場合は自動作成せず、状況と次の選択肢を提示する。

- working tree に未 commit の変更があり、それが PR に含まれるべきか判断できない。
- base branch が確定できない。
- PR template の必須項目が埋められない。
- PR body で参照する repository 内 artifact が base branch にも branch diff にも存在しない。
- 必要な review gate が未実施、または actionable finding が残っている。
- diff に secret、credential、private URL らしきものがある。
- 変更が複数の無関係な目的を含み、1つの PR として説明しづらい。

## Closeout Report

完了報告には次を含める。

- 作成または更新した PR URL。
- draft / ready のどちらで作成・更新したか。ready の場合はユーザーの明示指示。
- base / head branch。
- 使用した PR template。なければ `template なし`。
- 実行したテスト。未実行ならその理由。
- review gate の種類、実行した skill / command、結果。不要ならその理由。
