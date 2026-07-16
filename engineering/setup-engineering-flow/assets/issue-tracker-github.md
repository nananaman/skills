# Issue Tracker

Issue tracker 種別: GitHub Issue

## 配置

Issue はこのリポジトリの GitHub Issues で管理する。
作成・更新には `gh` CLI を使う。

## draft / polish の動作

- `draft-issue` は GitHub Issue の本文 draft を作り、確認を挟まず `gh issue create` を実行する。
- `polish-issue` は更新内容を提示し、確認後に issue body を更新する。
- PRD / Design Doc が関係する場合は、issue body に参照 link と必要十分な要約を含める。

## PRD / Design Doc との関係

PRD / Design Doc は repo 内 docs、GitHub Issue、Discussion、Wiki、または repo ごとの設定先に置いてよい。
Issue body には、実装に必要な要約と参照 link を含める。
