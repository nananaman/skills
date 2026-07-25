---
name: create-plan
description: 取得した issue や task を実装する前に、関連文書とコードを調査し、grilling で共有理解を作って、一時的な plans/<task>-<slug>.md を作成する。通常実装、永続 Design Doc、task 分解、実装済み diff のレビューだけの依頼では使わない。
disable-model-invocation: true
---

# Create Plan

`create-plan <issue>` を入口に、個別 task の実装で使う一時 plan を作る。
plan は implementation design contract だが、永続的な設計文書ではない。

## Prerequisites

次を読む。

```text
docs/agents/engineering-flow.md
docs/agents/issue-tracker.md
docs/agents/domain.md
```

対象 issue は tracker 設定に従って取得する。
参照された Design Doc、ADR、PRD と、判断に必要な関連コード・テスト・設定を読む。
repo-local 設定がなければ `setup-engineering-flow` を提案して止める。

## Workflow

1. 対象 issue の goal、scope、完了条件、上流の設計判断を確認する。
2. コードベースを調査し、現状、既存 pattern、変更境界、検証方法を確認する。
3. `grilling` を使い、共有理解に必要な問いを一度に一つずつ解消する。
   - なぜ必要か
   - 何を満たせば完成か
   - 壊してはいけない制約
   - 責務と interface の境界
   - 正しさを判定する振る舞い
4. 重要な未決定事項がなくなったら `plans/<task-id>-<short-slug>.md` を作る。
   - task ID がない場合は `<short-slug>.md` にする。
   - 同じ task の plan が既にある場合は上書きせず、再開・置換・中止のどれかを確認する。
   - `plans/*.md` を `.gitignore` に追加しない。
5. 作成した plan が ignored / tracked ではなく、untracked として可視であることを確認する。

   ```bash
   git check-ignore --no-index <plan-path>
   git ls-files --error-unmatch <plan-path>
   git status --short --untracked-files=all -- <plan-path>
   ```

   `git check-ignore` または `git ls-files` が path を返した場合は lifecycle contract を満たさないため停止する。
   `git status` が `?? <plan-path>` を示さない場合も停止し、既存 rule / index の状態を報告する。
6. plan を読み直し、別セッションの coding agent が追加の設計判断なしに実装・検証できることを確認する。

## Plan Contract

標準の見出しは次の5つだけとする。

```md
# <title>

## 目的

## 現状

## 設計方針

## 完了条件

## スコープ外
```

参照、制約、変更対象、検証、採用しない案は、関係する章へ自然に書く。
task 固有で必要なら、ロールバック、手作業、関連 issue などの見出しを追加してよい。
局所的な構文や意味のない逐次編集手順は固定しない。

## Lifecycle

- plan file は作業中だけ存在する untracked file であり、一度も commit しない。
- 実装・検証・review・修正が終わるまでは plan を保持する。
- 通常は完成した変更を最初の実装 commit としてまとめる。
- commit 時は plan 原文を commit body の marker 内へ取り込み、その後 plan file を削除する。
- 途中 commit が必要な場合は、最初の commit body に plan を取り込むが、file は実装完了まで保持し、最後の commit 前に削除する。

```text
Implementation-Plan:

<plan 原文>

End-Implementation-Plan
```

## Safety

- plan 作成中に正式な実装 diff を作らない。
- 既存のユーザー変更を戻さない。
- plan file の commit、`.gitignore` への追加、tracker 更新、commit、push は行わない。

## Completion

- plan file の location を報告した。
- 解消した重要判断と、参照した issue / 永続設計文書を報告した。
- plan に実装を block する未解決事項がない。
- plan file が ignored / tracked ではなく、`git status` で untracked として可視である。
- 実装へ進めるかを報告した。
