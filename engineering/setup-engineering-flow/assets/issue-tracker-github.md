# Issue tracker

Issue tracker 種別: GitHub Issue

## 配置

Issue はこのリポジトリの GitHub Issues で管理する。
作成・更新には `gh` CLI を使う。

## task 作成

- `task-breakdown` は task 分解案を提示し、ユーザー確認後に `gh issue create` を実行する。
- Issue は共有する作業範囲として書き、個別実装の plan は含めない。
- PRD / Design Doc / ADR が関係する場合は、issue body に参照 link と task の境界に必要な要約を含める。
- 担当者は issue を取得した後、`create-plan <issue>` で一時 plan を作る。

## 永続文書との関係

PRD / Design Doc / ADR は repo 内 docs、GitHub Issue、Discussion、Wiki、または repo ごとの設定先に置いてよい。
Issue body には、task の目的と境界を理解するための要約と参照 link を含める。
