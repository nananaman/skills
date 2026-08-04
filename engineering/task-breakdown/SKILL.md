---
name: task-breakdown
description: Design Doc、ADR、PRD、会話上の合意、ユーザー説明から、独立して担当・実行できる task 群へ分解する。依存関係と作業境界を整理し、確認後に repo 設定済みの GitHub Issue、local markdown、Asana などへ作成する。実装 plan、コード変更、既存 issue の詳細化だけの依頼では使わない。
disable-model-invocation: true
---

# タスク分割

合意済みの要求や設計を、担当者が取得できる task 群へ分解する。
issue は共有する作業単位であり、個別実装の設計契約にはしない。

## 前提条件

次の repo-local 設定を読む。

```text
docs/agents/engineering-flow.md
docs/agents/issue-tracker.md
docs/agents/domain.md
```

設定がなければ `setup-engineering-flow` を提案して止める。
入力は Design Doc に限定しない。ADR、PRD、既存 issue、会話上の合意、ユーザー説明を使ってよい。
ただし task 分解に必要な要求や設計判断が未確定なら、分解で補わず上流の文書または `grilling` へ戻す。

## タスクの契約

各 task には、担当範囲を共有するために必要な情報だけを含める。

- 目的
- 対象範囲
- 対象外
- 完了条件
- 依存する task
- 元になった要求・設計への参照
- 必要な場合だけ、担当 component や変更してよい interface 境界

ファイルごとの編集手順、関数内部の実装方法、テストの具体的な書き方など、担当者が実装前に決める内容は入れない。

## 手順

1. 入力と関連する永続文書を読み、タスク全体が達成する目標と制約を確認する。
2. 独立して担当・検証できる境界へ分解する。
   - task ごとに外部から判定できる完了条件を持たせる。
   - 同じ責務を複数 task に重複させない。
   - 並行実行できない task は依存関係と順序を明示する。
   - 統合時に初めて判明する作業があれば、独立した integration task にする。
3. task 一覧を作成前に提示する。
   - title
   - 目的と範囲の要約
   - 依存関係
   - 並行実行可能性
   - 作成先 tracker
4. ユーザー確認後だけ `docs/agents/issue-tracker.md` に従って作成する。
   - GitHub Issue：`gh issue create`
   - ローカル Markdown：設定済みのディレクトリ、ファイル名、`SEQUENCE` 規則
   - その他：Asana、Jira、Linear などの設定文書にある操作と権限規則
5. 作成した issue の URL / path と依存関係を報告する。

## 安全上の制約

- tracker へ作成する前に分解案の確認を得る。
- 既存 issue の変更、close、担当者設定、label 変更は、分解案の作成とは別の変更として扱う。
- commit、push、APM pin 更新、install、実装は行わない。

## 完了条件

- 合意済みの情報が、重複せず独立実行可能な task 群へ分かれている。
- 各 task の範囲、完了条件、依存関係、参照元が確認できる。
- ユーザー確認後、設定済み tracker に全 task が作成され、location が報告されている。
- 各 task の次の入口として `create-plan <issue>` が案内されている。
