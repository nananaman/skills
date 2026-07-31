---
name: create-plan
description: issue、task、またはユーザーの実装依頼から、関連文書とコードを調査し、grilling で共有理解を作って、一時的な plan file を作成し、独立reviewを通して実装readyにする。repo-local engineering-flow 設定の有無を問わず使える。通常実装、永続 Design Doc、task 分解、実装済み diff のレビューだけの依頼では使わない。
disable-model-invocation: true
---

# Create Plan

`create-plan <issue-or-task>` を入口に、個別実装で使う一時 plan を作る。
plan は implementation design contract だが、永続的な設計文書ではない。

## Context discovery

次の repo-local 設定が存在すれば読む。

```text
docs/agents/engineering-flow.md
docs/agents/issue-tracker.md
docs/agents/domain.md
```

これらは任意の追加 context であり、存在しないことを停止条件にしない。
設定がなければ `AGENTS.md`、`CLAUDE.md`、repository 内の関連文書、ユーザー入力から必要な規則と goal を特定する。

入力が issue identifier で、issue tracker 設定がある場合はその設定に従って取得する。
設定がなくても tracker を入力から一意に特定できる場合は取得してよい。
issue がない場合は、ユーザーの task 説明を plan の入口として扱う。
参照された Design Doc、ADR、PRD と、判断に必要な関連コード・テスト・設定を読む。

repo-local flow を継続運用として保存したい場合だけ `setup-engineering-flow` を提案する。
今回の plan 作成を setup の完了で block しない。

## Workflow

1. issue、task、またはユーザー入力から goal、scope、完了条件、上流の設計判断を確認する。
2. コードベースを調査し、現状、既存 pattern、変更境界、検証方法を確認する。
3. 調査だけでは確定しない重要な設計判断があり、観察結果によって plan が変わりうる場合は、`prototype` を使って検証する。
   - 既存 code、test、文書で答えられる問い、単なる理解不足、局所的な実装詳細には使わない。
   - 技術的成立性には最小の単一 spike、代替案の判断には必要な数の比較案を選ぶ。
   - prototype が問いを解消できなければ成功扱いにせず、`grilling` へ戻る。
   - 作成と削除は [Prototype lifecycle](#prototype-lifecycle) に従う。
4. `grilling` を使い、共有理解に必要な問いを一度に一つずつ解消する。
   - なぜ必要か
   - 何を満たせば完成か
   - 壊してはいけない制約
   - 責務と interface の境界
   - 正しさを判定する振る舞い
5. 重要な未決定事項がなくなったら、repo-local flow に設定された directory へ plan を作る。設定がなければ `plans/` を使う。
   - issue / task ID がある場合は `<task-id>-<short-slug>.md` にする。
   - task ID がない場合は `<short-slug>.md` にする。
   - 同じ task の plan が既にある場合は上書きせず、再開・置換・中止のどれかを確認する。
   - plan directory / pattern を `.gitignore` に追加しない。
6. 作成した plan が ignored / tracked ではなく、untracked として可視であることを確認する。

   ```bash
   git check-ignore --no-index <plan-path>
   git ls-files --error-unmatch <plan-path>
   git status --short --untracked-files=all -- <plan-path>
   ```

   `git check-ignore` または `git ls-files` が path を返した場合は lifecycle contract を満たさないため停止する。
   `git status` が `?? <plan-path>` を示さない場合も停止し、既存 rule / index の状態を報告する。
7. plan を読み直し、別セッションの coding agent が追加の設計判断なしに実装・検証できることを確認する。
8. prototype を使った場合は、観察結果と設計判断が plan に残っていることを確認し、prototype 固有の file と diff を削除してから [Prototype lifecycle](#prototype-lifecycle) の cleanliness gate を通す。
9. `review-plan`でplanを独立評価する。
   - `revise` findingは、要求とrepository contextから一意に直せる範囲でplanへ反映し、fresh reviewerで再reviewする。
   - `investigate` findingは、安全な調査やproofで解消できる場合は実行し、planへ反映して再reviewする。
   - `decision` finding、上流設計の変更、scope拡大、追加authorityが必要な場合は、自動で決めずユーザーへ一度に一つ質問する。
   - 同じfindingが再発する、finding同士が矛盾する、または修正の複雑性が低減するriskに見合わない場合はloopを止め、blockedとして報告する。
   - `ready`以外の結果で実装可能と表現しない。

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

## Prototype lifecycle

`prototype` は plan の判断材料であり、正式な実装 diff ではない。
repository 内を含む、問いを適切に検証できる場所へ作成してよいが、次の境界を守る。

1. 作成前に `git status --short --untracked-files=all` と対象 path の diff を確認し、開始時からある tracked / untracked user changes と、prototype が触る path を記録する。
2. 開始時に dirty な path は編集しない。別 path、専用 route、fixture、adapter など、prototype 由来変更を分離できる足場を使う。
3. clean な既存 path を編集する場合は、開始時 baseline を復元可能に保持し、prototype 由来変更だけを除去できる境界を定める。新規 path は prototype 所有として列挙する。
4. user change と prototype change を安全に分離できなければ、その path を使う試作を中止して `grilling` へ戻る。別の検証方法でも重要判断を解消できない場合だけユーザーへ確認する。
5. 観察した事実と、それによって確定した判断を plan の該当章へ移す。
6. `review-plan` の前に prototype 固有の file と diff を削除する。削除はこの lifecycle の完了操作であり、開始時からある user changes を戻さない。
7. 削除後に `git status --short --untracked-files=all` と対象 path の diff を開始時の記録と比較し、開始時からある user changes と untracked plan file 以外の prototype 由来変更が残っていないことを確認する。

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
- 判断用 prototype は [Prototype lifecycle](#prototype-lifecycle) の範囲でのみ作成する。
- 既存のユーザー変更を戻さない。
- plan file の commit、`.gitignore` への追加、tracker 更新、commit、push は行わない。

## Completion

- plan file の location を報告した。
- 解消した重要判断と、参照した issue / 永続設計文書があれば報告した。
- plan に実装を block する未解決事項がない。
- `review-plan`が`ready`を返し、accepted `blocker`が残っていない。
- plan file が ignored / tracked ではなく、`git status` で untracked として可視である。
- prototype を使った場合は、判断と根拠が plan に保存され、prototype 由来変更が review 前に削除されている。
- 実装へ進めるかを報告した。
