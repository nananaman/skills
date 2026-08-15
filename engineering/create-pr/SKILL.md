---
name: create-pr
description: 現在の branch から GitHub PR を作成する。通常は draft にし、ready PR はユーザー明示指示時だけ許可する。PR template、diff、commit、テスト状況を整理する。
disable-model-invocation: true
---

# PR の作成

現在の branch から、reviewer がすぐ読める GitHub PR を作成する。通常は draft PR にし、ready PR はユーザーが明示的に指示した場合だけ許可する。既存 PR がある場合は重複作成せず、更新または中止を提案する。

## 原則

- PR 方針は `chouge-git` の Pull Request 節に従う。
- 作成する PR は通常 draft にする。ready PR で作成するのは、ユーザーが明示的に ready PR 作成を指示した場合だけにする。
- project 規則が ready PR 作成を求めていても、ユーザーの明示指示がなければ draft で作成する。
- project に PR template がある場合は、その構成を優先して body を作る。
- PR body は実際の diff、commit、テスト状況と一致させる。
- branch の commit body に `Implementation-Plan:` marker がある場合は、plan 原文を PR body の折りたたみに転記する。
- uncommitted changes、未 push、base branch 不明、既存 PR などの状態を確認してから作成する。
- push または PR 作成の前に、変更種別に応じた review gate が通っていることを確認する。
- history rewrite、force push、commit 整理はこの skill の責務外。必要なら別作業として提案する。

## 手順

1. 現在の repository 状態を確認する。

   ```bash
   git status --short
   git branch --show-current
   git remote -v
   gh repo view --json nameWithOwner,defaultBranchRef
   ```

2. base branch を決める。
   - 既存 PR がある場合は `gh pr view --json baseRefName,headRefName,url,state,isDraft,title,body` を見る。
   - 既存 PR が `MERGED` ならその head branch を新しい変更に再利用せず、[既存 PR の扱い](#既存-pr-の扱い)に従って最新 base から新しい branch へ分ける。
   - 既存 PR がなければ GitHub default branch を使う。
   - ユーザーが base を指定している場合はそれを優先する。

3. branch の差分を読む。

   ```bash
   git fetch origin <base>
   git log --oneline --decorate origin/<base>..HEAD
   git diff --stat origin/<base>...HEAD
   git diff --name-status origin/<base>...HEAD
   ```

   commit message も全文読む。

   ```bash
   git log --format=fuller origin/<base>..HEAD
   ```

   `Implementation-Plan:` から `End-Implementation-Plan` までがある場合は、開始・終了 marker が一組で、内容が空でないことを確認する。
   marker が壊れている場合や複数の plan があり対象を判断できない場合は PR body を作らず停止する。

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
   - UI変更でscreenshot / videoを添付する場合は、添付前に成果物を実際に開いて目視確認する。実際のaffected route / screenと変更後stateが写り、PR bodyに記載するplatform、device、viewportと一致することを確認する。意図したevidenceでないscaffold、mock専用画面、splash、loading中の状態は添付しない。capture commandの成功、ファイル名、UI testのassertionだけで代替しない。
   - PR body で local markdown issue / Design Doc / changelog などの repository 内 artifact を参照する場合は、その artifact が base branch に既に存在するか、今回の branch diff に含まれているかを確認する。存在しない artifact を参照する PR body は作らない。
   - 大きすぎる PR なら、PR 作成前に split を提案する。

6. PR title / body の下書きを作る。
   - template がある場合は見出しや checklist を保ち、空欄を実 diff に基づいて埋める。
   - template がない場合は次の構成を使う。

   ```md
   ## 概要
   - 

   ## 変更内容
   - 

   ## テスト
   - 
   ```

   `Tests` には、実行したコマンドを書く。未実行なら `未実行` と理由を書く。推測で「テスト済み」と書かない。
   `review-diff-code`、`skill-workbench` 差分レビューなど内部レビュー運用の実施内容(reviewer 構成、指摘内容、採否理由など)は PR body に書かない。実施自体は step 7 の review gate として行う。

   commit body に implementation plan がある場合は、template の末尾または標準 body の末尾へ次を追加する。
   plan 用の見出しは追加せず、`<details>`、`<summary>Implementation plan</summary>`、`</details>` を PR body に literal な HTML tag として含める。

   ```md
   <details>
   <summary>Implementation plan</summary>

   <commit body の marker 内にある plan 原文>

   </details>
   ```

   `Implementation-Plan:` と `End-Implementation-Plan` の marker 自体は転記せず、その間の plan 原文だけを要約・編集せずに入れる。
   marker 内と折りたたみ内が一致することを確認する。
   PR 作成前に body file を読み直し、opening tag、summary、closing tag がそれぞれ一つあり、この順で並んでいることを確認する。欠けている場合は PR を作成しない。

7. review gate を確認する。
   - docs-only の変更なら review gate は不要。
   - skill 変更を含むなら `skill-workbench` の差分レビューを使う。
   - コード、設定、テスト、CI、実行時の動作に影響する変更を含むなら `review-diff-code` skill を使い、実際の基点または変更のある作業ツリーを一度評価して指摘の採否台帳を確認する。
   - 既に同じ base / head diff に対して review 済みなら再実行しなくてよい。
   - 会話や直近の作業ログで review 済みと確認できなければ、未実施として扱う。PR body は review 済み判定の根拠にしない。
   - 未実施なら push 前に実行する。push が不要な場合でも、PR 作成前に実行する。
   - 対応可能な指摘が残る場合は、push や PR 作成へ進まない。
   - review gate の結果は PR body に書かず、完了報告でユーザーに伝える。

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

9. 作成後に PR body を取得して確認する。

   ```bash
   gh pr view --json body,url
   ```

   implementation plan がある場合は、作成前と同じ三つの tag が GitHub 上の body に literal に保存され、plan がその内側にあることを確認する。満たさない場合は完了とせず、正しい body file を使って修正する。

10. URL と reviewer 向け要点を報告する。

## 既存 PR の扱い

同じ branch に既存 PR がある場合は、重複作成しない。

```bash
gh pr view --json url,state,isDraft,title,body,baseRefName,headRefName
```

- 既存 PR が draft なら、必要に応じて `gh pr edit --title ... --body-file ...` で更新する。
- 既存 PR が ready for review なら、draft に戻せない前提で扱い、更新してよいか確認する。
- 既存 PR が merged なら、その head branch へ新しい commit を追加しない。base を fetch し、現在の `HEAD` が `origin/<base>` の ancestor で、uncommitted changes を失わずに switch できる場合だけ、branch naming 規約に従って最新 `origin/<base>` から新しい branch を作る。それ以外は停止し、branch 分割または commit の載せ替え案を提示する。
- closed PR しかない場合は、新規作成してよいか確認する。

## テンプレートの扱い

template を使うときは、次を守る。

- checklist を削除しない。該当しない項目は未チェックのまま理由を書く。
- issue link、screenshot、migration、rollout など project 固有の欄を勝手に省略しない。
- template の文言と矛盾する内容を書かない。
- template の要求情報が diff から分からない場合は、PR 作成前にユーザーへ質問する。
- template にレビュー記録相当の欄がある場合も、`review-diff-code` などの内部レビュー運用の実施内容は書かない。欄の趣旨に沿う範囲(例: 人間 reviewer への依頼事項)だけを埋める。

## 安全確認

次の場合は自動作成せず、状況と次の選択肢を提示する。

- working tree に未 commit の変更があり、それが PR に含まれるべきか判断できない。
- base branch が確定できない。
- PR template の必須項目が埋められない。
- PR body で参照する repository 内 artifact が base branch にも branch diff にも存在しない。
- implementation plan marker が不完全、空、または対象を一意に決められない。
- 必要なレビュー判定が未実施、または対応可能な指摘が残っている。
- diff に secret、credential、private URL らしきものがある。
- 変更が複数の無関係な目的を含み、1つの PR として説明しづらい。

## 完了報告

完了報告には次を含める。

- 作成または更新した PR URL。
- draft / ready のどちらで作成・更新したか。ready の場合はユーザーの明示指示。
- base / head branch。
- 使用した PR template。なければ `template なし`。
- 実行したテスト。未実行ならその理由。
- review gate の種類、実行した skill / command、結果。不要ならその理由。
- implementation plan を転記したか。なければ `plan marker なし`。
