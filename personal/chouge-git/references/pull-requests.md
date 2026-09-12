## プルリクエスト

- PR は通常 draft で作成する。ready PR で作成するのは、ユーザーが明示的に ready PR 作成を指示した場合だけにする。
- project 規則が ready PR 作成を求めていても、ユーザーの明示指示がなければ draft で作成する。ready 化は人間の確認後に行う。
- PR title / body / reviewer 向け説明は、project に明文化された言語指定がない限り日本語で書く。
- PR body は実際の diff、commit、テスト状況と一致させる。
- 実際の挙動変更が、本 PR の diff に含まれない作業(secret/設定値の投入、別リポジトリでの対応、手動デプロイ・確認など)に依存し、merge だけでは完了しない場合、title と body 冒頭で完了しないことが伝わるように書き、残作業をチェックリストとして列挙する。
- project に PR template がある場合は、その構成を優先する。
- PR body には `review-diff-code`、`skill-workbench` 差分レビューなど、個人的な内部レビュー運用の実施内容(reviewer 構成、指摘内容、採否理由など)を書かない。レビュー要否と完了条件は `implement` に従い、既に評価した同じ差分は再レビューしない。
