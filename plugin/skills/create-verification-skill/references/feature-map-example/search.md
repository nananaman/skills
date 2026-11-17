# ノートを検索する

タイトルまたは本文でノートを検索し、一致したノートを開ける。検索完了後の該当なしと、検索不能を区別する。

## サブ機能

- `search-open`：各ブラウザ入口で検索を開く。
- `search-match`：タイトル・本文で一致し、データは変更しない。
- `search-open-result`：検索結果を開く。
- `search-empty`：該当なしを表示する。
- `search-clear`：入力を消し、最近のノートに戻る。
- `search-cli`：端末でも同じ一致結果を取得する。

## 利用者から見た入口

- ツールバーの `Search` ボタン。
- 編集欄の外にフォーカスがある状態で `/` キー。
- 端末で `notes search <query>`。

## control-notes での操作

前提：共通の初期状態で `doctor` が成功し、`Quarterly plan` の本文に `Draft budget` がある。

- **ボタン**：`control-notes browser click --role button --name "Search"`。`Search notes` ダイアログが開き、searchbox にフォーカスする。
- **キーボード**：ダイアログを閉じてページにフォーカスし、`control-notes browser press --key "/"`。同じダイアログが開き、ページに `/` は入力されない。
- **タイトル一致**：`control-notes browser fill --role searchbox --name "Search notes" --value "quarterly"`。検索完了後、`Search results` に `Quarterly plan` があり、`Grocery list` はない。
- **一致の証拠**：この状態で `control-notes browser snapshot --aria --path "$EVIDENCE_DIR/search-results.aria.txt"` と `control-notes browser screenshot --path "$EVIDENCE_DIR/search-results.png"`。アプリ、検索語、一致結果が分かることを確認する。
- **本文一致**：同じ fill コマンドの value を `budget` に変える。`Quarterly plan` と本文の一致箇所が表示される。
- **結果を開く**：`control-notes browser click --role link --name "Quarterly plan"`。ダイアログが閉じ、エディターの見出しが `Quarterly plan` になる。
- **該当なし**：検索を再度開き、同じ fill コマンドの value を `volcano` にする。処理完了後に `No matching notes` が現れる。
- **クリア**：`control-notes browser click --role button --name "Clear search"`。searchbox が空になり、結果一覧が `Recent notes` に変わる。
- **CLI 一致**：`control-notes cli -- notes search "quarterly" --format json`。終了コード `0`、stdout にタイトル `Quarterly plan` の一件がある。
- **CLI 該当なし**：`control-notes cli -- notes search "volcano" --format json`。終了コード `0`、stdout は `[]`。
- **記録**：各入口の操作と結果、CLI の stdout・stderr・終了コードを証拠先へ保存する。クリア後の画面を一致の証拠にしない。

## 注意点

- 編集欄内の `/` は文字入力になる。
- debounce があるため、固定時間待つのではなく結果または該当なしの表示を待つ。
- アーカイブ済みノートは `Include archived` を有効にしないと検索対象にならない。
- CLI の既定出力は人向け。検証には `--format json` を使う。
- 結果を開くと画面が変わる。別の検索を試す前に再度検索を開く。
