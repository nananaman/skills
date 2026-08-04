# Issue tracker

Issue tracker 種別: other

## 運用

この tracker の運用を prose で記録する。
次を含める。

- issue がどこにあるか
- 新しい issue をどう作るか
- 既存 issue をどう更新するか
- PRD / Design Doc / ADR への参照をどう書くか
- task 作成前の確認方法
- エージェントが守るべきラベル、状態、担当者、権限ルール

## エージェントのルール

この tracker が設定されている場合、`task-breakdown` と `create-plan` は GitHub Issue やローカル Markdown の挙動を仮定しない。
`task-breakdown` は分解案を提示し、ユーザー確認後だけ上記の手順に従ってタスクを作成する。
既存成果物の変更やタスク作成を超える不可逆な tracker 操作の前にはユーザー確認を取る。
