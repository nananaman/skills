---
name: task-breakdown
description: Design Doc、ADR、PRD、会話上の合意、ユーザー説明を独立実行可能な task 群へ分解する。repo-local 設定がなくても分解案を作り、作成先と内容の許可がある場合に tracker へ作成する。実装 plan、コード変更、既存 issue の詳細化だけの依頼では使わない。
disable-model-invocation: true
---

# タスク分割

合意済みの要求・設計を、独立して担当・検証できる task 群に分ける。
入力は Design Doc、ADR、PRD、issue、会話上の合意を使う。未決定の要求・設計は分割で補わない。

## task の契約

各 task に目的、対象範囲・対象外、完了条件、依存関係、参照元を持たせる。
責務の重複を避け、並行実行できない作業や統合時の検証を依存関係として表す。
担当者が決められるファイル編集順・関数内部・テストの書き方は固定しない。

## 作成先と成果

repo-local の `docs/agents/engineering-flow.md`・`issue-tracker.md`・`domain.md` があれば使う。
設定がなくても分解案は作れる。tracker と命名・採番規則は依頼や既存運用から特定する。

提案の依頼では task 一覧と依存関係を返す。
作成の依頼では許可された tracker に作成して URL / path を報告する。内容や作成先の判断が不足する部分は案として示す。
各 task の実装計画は `create-plan <issue>` で扱う。
