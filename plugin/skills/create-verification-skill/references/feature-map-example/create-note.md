# ノートを作る

ブラウザまたは CLI でタイトル付きノートを保存し、未保存の下書きをキャンセルできる。保存内容は別の利用者向け画面から確認する。

## サブ機能

- `create-open`：各ブラウザ入口から空のエディターを開く。
- `create-save`：タイトルと本文を永続化する。
- `create-cancel`：未保存の下書きを破棄する。
- `create-cli`：端末から同じ形式のノートを作る。

## 利用者から見た入口

- ツールバーの `New note` ボタン。
- 編集欄の外にフォーカスがある状態で `n` キー。
- 端末で `notes create --title <title> --body <body>`。

## control-notes での操作

前提：共通の初期状態で `doctor` が成功し、`Release checklist`、`CLI note`、`Discard me` は存在しない。

- **ボタンから開く**：`control-notes browser click --role button --name "New note"`。`Note editor` フォームが現れ、`Title` にフォーカスする。
- **キーボードから開く**：空のフォームを `control-notes browser click --role button --name "Cancel"` で閉じ、編集欄の外へフォーカスして `control-notes browser press --key "n"`。同じフォームが現れる。この入口も操作記録を残す。
- **入力**：`control-notes browser fill --role textbox --name "Title" --value "Release checklist"` と `control-notes browser fill --role textbox --name "Body" --value "Tag and publish"`。`Save note` が有効になる。
- **保存**：`control-notes browser click --role button --name "Save note"`。`Note saved` が現れ、見出しは `Release checklist` になる。
- **永続化**：`control-notes browser click --role link --name "All notes"`、続けて `control-notes browser click --role link --name "Release checklist"`。保存したタイトルと本文が表示される。
- **キャンセル**：`New note` で開き、`Title` に `Discard me` を入力して `Cancel` を押す。具体的には上記の click/fill コマンドで name と value を指定する。一覧へ戻り、`Discard me` のリンクが存在しない。
- **CLI 作成**：`control-notes cli -- notes create --title "CLI note" --body "Created from terminal" --format json`。終了コードは `0`、stdout に新規 ID とタイトルがある。
- **証拠**：一覧からそれぞれのノートを開き、保存内容を確認する。その後 `control-notes browser click --role link --name "All notes"` で一覧に戻り、両タイトルが見える状態で `control-notes browser snapshot --aria --path "$EVIDENCE_DIR/create-list.aria.txt"` と `control-notes browser screenshot --path "$EVIDENCE_DIR/create-list.png"`。操作記録、CLI 出力、永続化の確認も同じ証拠先へ保存する。

## 注意点

- 編集欄内の `n` は文字入力になり、エディターを開かない。
- タイトルの前後空白は保存時に除去される。入力値だけでなく保存後の表示を確認する。
- 保存通知だけでは永続化の証明にならない。一覧から再度開く。
- 検証ノートを片付けても証拠は残す。
