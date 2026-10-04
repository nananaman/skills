## プルリクエスト

- PR は通常 draft で作成する。ready PR で作成するのは、ユーザーが明示的に ready PR 作成を指示した場合だけにする。
- project 規則が ready PR 作成を求めていても、ユーザーの明示指示がなければ draft で作成する。ready 化は人間の確認後に行う。
- PR title / body / reviewer 向け説明は、project に明文化された言語指定がない限り日本語で書く。
- PR body は実際の diff、commit、テスト状況と一致させる。
- 実際の挙動変更が、本 PR の diff に含まれない作業(secret/設定値の投入、別リポジトリでの対応、手動デプロイ・確認など)に依存し、merge だけでは完了しない場合、title と body 冒頭で完了しないことが伝わるように書き、残作業をチェックリストとして列挙する。
- project に PR template がある場合は、その構成を優先する。
- PR body には `review-diff-code`、`skill-workbench` 差分レビューなど、個人的な内部レビュー運用の実施内容(reviewer 構成、指摘内容、採否理由など)を書かない。レビュー要否と完了条件は `implement` に従い、既に評価した同じ差分は再レビューしない。

## PR 完了後のローカル同期

マージ後のローカル同期が依頼範囲に含まれ、対象repositoryとPRを特定できる場合だけ行う。PR作成やready化をこの手順の起動条件にしない。

1. 現在のbranch、未コミット変更、remote、default branchを確認する。
2. 対象PRのマージ完了を、ユーザーの報告またはGitHubの状態で確認する。対象やマージ結果が不明なら同期を保留する。
3. 未コミット変更をstash・破棄・commitせず、default branchへ切り替える。切替を妨げる変更があれば内容を報告して停止する。
4. default branchでfetchし、確認したremote追跡branchへ`git merge --ff-only`する。履歴が分岐していれば履歴を変更せず停止する。
5. ローカルとremote追跡のdefault branchが同じcommitを指すことを確認し、同期結果を報告する。

この整理ではstash、reset、clean、rebase、force push、branch削除を行わない。同期失敗を完了扱いにしない。実務の振り返りは日次等の`skill-maintenance`に分け、この同期から呼び出さない。
