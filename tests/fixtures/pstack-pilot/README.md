# native pilot用の小さなCLI

これは合成fixtureです。実サービス、認証情報、元の会話履歴を含みません。
初期版はJSONから全taskを読み、入力順で `id: title` を表示します。

```sh
python3 tasklist.py tasks.json
python3 -m unittest discover -s . -p 'test_*.py'
```

実行担当への依頼は次です。

> タスク一覧CLIへ `--status all|open|done` を追加してください。省略時は今の一覧・順序・表示を保ち、openは未完了、doneは完了だけを表示してください。未知のstatusは非ゼロ終了にし、入力ファイルを書き換えないでください。計画、設計、TDD、実装、実際のCLI検証、独立レビューをpstackで一巡し、日本語で結果を報告してください。外部への公開と反映は行わないでください。

受入担当は、初期の全件3行を保つこと、openが1・3、doneが2になること、空の一致結果が0行かつ成功になること、未知statusが失敗することを確認します。
入力JSONの前後hash、最後の関連編集後のtest出力、実CLIのstdout・stderr・exit codeを保存します。
実装担当とは別の文脈で最終treeを確認し、staticなコード確認をCLI実行の成功へ転用しません。

このfixtureにはremoteがありません。
draft PR段階は、別途指定した本人管理repoの実変更で確認します。
fixture内のローカルPR文案は、GitHub上のdraft PR作成の代替ではありません。
