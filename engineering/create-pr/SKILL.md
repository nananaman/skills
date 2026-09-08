---
name: create-pr
description: 現在の branch から GitHub PR を作成する。通常は draft にし、ready PR はユーザー明示指示時だけ許可する。PR template、diff、commit、テスト状況を整理する。
disable-model-invocation: true
---

# PR の作成

現在の変更をレビューできる GitHub PR にする。Git・権限・draft / ready の方針は `chouge-git` に従う。

## 対象の確認

branch、remote、既存 PR、base、未コミット差分を確認する。base の指定がなければ GitHub の default branch を使う。
base を fetch し、commit 本文と `base...HEAD` が今回の目的だけを含むことを確かめる。
既存の open PR は更新し、merged PR の branch は再利用しない。

完成差分のレビューは `implement` の「レビュー範囲の選択」に従う。既に確認済みの差分を、PR 作成だけを理由に再レビューしない。

## 本文

repository の PR template を優先し、なければ概要・変更内容・テストを書く。
実際の diff と検証結果に基づき、merge 後に必要な作業を明記する。内部レビューの手順や採否台帳は載せない。
UI 変更には、対象画面の変更後を撮影して目視確認した screenshot または video を添付する。
repository 内の成果物を参照する場合は base または今回の差分に存在するものを使う。

### 実装計画の転記

commit 本文に `Implementation-Plan:` と `End-Implementation-Plan` がある場合、その間の原文を次の形式で転記する。

```html
<details>
<summary>Implementation plan</summary>

<plan 原文>

</details>
```

marker が不完全・空・曖昧なら、plan を推測せず公開を保留する。

## 作成と確認

本文を一時ファイルに保存し、必要な push 後に `gh pr create --draft --base <base> --head <branch> --title <title> --body-file <file>` で作成する。
ready の明示依頼がある場合だけ `--draft` を外す。既存 PR は `gh pr edit` で更新する。
GitHub 上の本文と draft 状態を取得して確かめ、plan がある場合は原文と折りたたみの保存も確認する。
PR URL、主要な変更、検証結果を報告する。
