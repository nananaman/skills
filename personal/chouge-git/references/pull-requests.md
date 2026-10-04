## プルリクエスト

- PR は通常 draft で作成する。ready PR で作成するのは、ユーザーが明示的に ready PR 作成を指示した場合だけにする。
- project 規則が ready PR 作成を求めていても、ユーザーの明示指示がなければ draft で作成する。ready 化は人間の確認後に行う。
- PR title / body / reviewer 向け説明は、project に明文化された言語指定がない限り日本語で書く。
- PR body は実際の diff、commit、テスト状況と一致させる。
- 実際の挙動変更が、本 PR の diff に含まれない作業(secret/設定値の投入、別リポジトリでの対応、手動デプロイ・確認など)に依存し、merge だけでは完了しない場合、title と body 冒頭で完了しないことが伝わるように書き、残作業をチェックリストとして列挙する。
- project に PR template がある場合は、その構成を優先する。
- PR body には `review-diff-code`、`skill-workbench` 差分レビューなど、個人的な内部レビュー運用の実施内容(reviewer 構成、指摘内容、採否理由など)を書かない。レビュー要否と完了条件は `implement` に従い、既に評価した同じ差分は再レビューしない。

## PR本文の画像

説明専用のスクリーンショット・比較画像はrepo外の作業pathに置き、commit前に`git diff --cached --name-only`で混入していないことを確認する。
`gh pr edit --help`で[正式な`--attach`](https://cli.github.com/manual/gh_pr_edit)への対応を確認し、対象repo・PR番号を明示して添付する。

```sh
gh pr edit <PR番号> --repo <owner/repo> \
  --attach '/tmp/pr-screenshot.png#変更後の画面'
```

body指定なしなら既存本文を保持し、アップロードした画像への参照を末尾に追加する。本文内の位置を指定する場合は、既存内容を保った`--body-file`に画像pathのMarkdown参照を置き、同じ画像を`--attach`する。
部分成功でも本文が更新されるため、`gh pr view <PR番号> --repo <owner/repo> --json body`で参照を読み戻し、再試行は未添付分だけにする。未対応・権限不足・添付失敗は報告し、説明用画像をcommitへ追加して代用しない。
