# 公開契約

`build_actions(labels, *, disabled=False)` は、labels と同じ順序で
`{"label": label, "disabled": disabled}` の辞書を返す。
省略時はすべて有効。空の入力は空のリストを返す。
`disabled` はキーワード専用引数で、別名は提供しない。
外部利用者はこのシグネチャに依存している。

この課題のテスト実行: `cd api && python3 -m unittest -v`
