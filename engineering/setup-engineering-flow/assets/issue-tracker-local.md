# Issue Tracker

Issue tracker 種別: local markdown

## 配置

Issue は次のディレクトリで管理する。

```text
docs/issues/
```

完了した issue は必要に応じて次へ移動してよい。

```text
docs/issues/closed/
```

## 採番

`docs/issues/SEQUENCE` は最後に使った issue 番号を保持する。

例:

```text
SEQUENCE=42
次の issue: docs/issues/0043-short-title.md
作成後: SEQUENCE=43
```

`SEQUENCE` が存在する場合、filename から次番号を推測しない。
`SEQUENCE` が欠落している場合だけ、ユーザー確認後に復旧方法を決める。

## ファイル名

issue 番号は 4 桁 zero padding にする。

```text
NNNN-short-kebab-title.md
```

例:

```text
0001-add-login-form.md
0043-refactor-session-state.md
```

## 参照

PRD / Design Doc から issue を作る場合でも、issue 番号に feature ID を埋め込まない。
PRD / Design Doc との関係は issue 本文の `参照` に link として書く。
