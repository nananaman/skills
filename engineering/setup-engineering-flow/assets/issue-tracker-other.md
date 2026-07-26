# Issue Tracker

Issue tracker 種別: other

## 運用

この tracker の運用を prose で記録する。
次を含める。

- issue がどこにあるか
- 新しい issue をどう作るか
- 既存 issue をどう更新するか
- PRD / Design Doc / ADR への参照をどう書くか
- task 作成前の確認方法
- agent が守るべき label、state、owner、権限ルール

## Agent ルール

この tracker が設定されている場合、`task-breakdown` と `create-plan` は GitHub Issue や local markdown の挙動を仮定しない。
`task-breakdown` は分解案を提示し、ユーザー確認後だけ上記 workflow に従って task を作成する。
既存 artifact の変更や task 作成を超える不可逆な tracker 操作の前にはユーザー確認を取る。
