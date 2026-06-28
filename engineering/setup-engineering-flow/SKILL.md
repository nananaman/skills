---
name: setup-engineering-flow
description: リポジトリごとの engineering flow を初期設定する。issue tracker、PRD / Design Doc の配置、local markdown issue の採番、AGENTS.md / CLAUDE.md の参照 block を整える。draft-issue / polish-issue の初回利用前に user-invoked で実行する。通常の issue 作成・issue polish・実装・レビューでは使わない。
disable-model-invocation: true
---

# Setup Engineering Flow

`draft-issue` と `polish-issue` が前提にする repo-local 設定を作る。
これは一度だけ実行する prompt-driven skill であり、deterministic script ではない。

## 目的

次を repo ごとの source of truth として記録する。

- issue tracker: GitHub Issue / local markdown / other
- PRD / Design Doc の置き場所
- engineering flow: PRD → Design Doc? → draft issue → polish issue → implementation → review
- local markdown issue の採番規則
- agent が読む `AGENTS.md` / `CLAUDE.md` の参照 block

## 原則

- 質問は一度に一つだけ行う。
- 既存運用を探索してから提案する。存在する `docs/`, `issues/`, `.github/`, `AGENTS.md`, `CLAUDE.md` を無視しない。
- ユーザーに用語を説明してから選択肢を出す。
- draft を提示して確認してから書く。
- 既存 `AGENTS.md` / `CLAUDE.md` を全面 rewrite しない。
- managed block marker がある場合だけ marker 内を置換する。marker がなければ末尾に追加し、周辺本文は触らない。
- 書き込み対象ファイルに未 commit の変更がある場合は、merge 方針を確認するまで書かない。
- commit / push / APM pin / install は行わない。

## Workflow

### 1. Explore

現在の repo を調べる。

```bash
git remote -v
git status --short
```

確認するもの:

- `AGENTS.md`, `CLAUDE.md`
- `docs/agents/`
- `docs/prd/`, `docs/design/`, `docs/issues/`
- `issues/`, `issues/SEQUENCE`
- `.github/ISSUE_TEMPLATE/`, `.github/ISSUE_TEMPLATE.md`
- GitHub remote の有無
- 既存 issue / PRD / design doc らしいファイル

### 2. Present findings

存在するもの・存在しないものを短く報告する。
次の判断を一つずつ確認する。

#### A. Issue tracker

説明: issue tracker は実装作業単位を管理する場所である。
`draft-issue` と `polish-issue` はここを読んで issue を作成・更新する。

選択肢:

- GitHub Issue: `gh` CLI で issue を作成・更新する
- Local markdown: repo 内 markdown file として管理する
- Other: Jira / Linear など。ユーザーの説明を prose で記録する

GitHub remote がある場合は GitHub を提案する。
`docs/issues/` または `issues/` がある場合は local markdown も有力候補として示す。

#### B. PRD / Design Doc location

説明: PRD は「なぜ・何を・どこまで」を固定する文書で、Design Doc は「どう設計するか」を固定する文書である。
Design Doc には必要に応じて Glossary / Domain Model を含める。

デフォルト:

```text
docs/prd/
docs/design/
```

ただし GitHub Issue / Discussion / Wiki / other location も許可する。

#### C. Local markdown issue convention

local markdown を使う場合だけ確認する。
デフォルト:

```text
docs/issues/SEQUENCE
docs/issues/0001-short-title.md
docs/issues/closed/0002-done.md
```

`SEQUENCE` は「最後に使った番号」を表す。

```text
SEQUENCE=42 -> 次は 0043 -> 作成後 SEQUENCE=43
```

既存 `issues/SEQUENCE` がある場合は、その場所を使うか `docs/issues/` に移行するか確認する。

#### D. AGENTS.md / CLAUDE.md update

説明: repo-local rule を agent が毎回発見できるように、`AGENTS.md` または `CLAUDE.md` に参照 block を置く。

選択規則:

- `CLAUDE.md` があればそれを更新する
- なければ `AGENTS.md` を更新する
- 両方なければ、どちらを作るか質問する

### 3. Draft files

書き込む前に、次の draft を提示してユーザーの確認を得る。

- `docs/agents/engineering-flow.md`
- `docs/agents/issue-tracker.md`
- `docs/agents/domain.md`
- `AGENTS.md` / `CLAUDE.md` に入れる block

seed として assets を読む。

- 常に読む: `assets/engineering-flow.md`, `assets/domain.md`
- GitHub Issue を選んだ場合だけ読む: `assets/issue-tracker-github.md`
- Local markdown を選んだ場合だけ読む: `assets/issue-tracker-local.md`
- Other を選んだ場合だけ読む: `assets/issue-tracker-other.md`

選択していない tracker の asset は読まない。不要な SEQUENCE 規則や tracker prose を混入させない。

### 4. Write

確認後に以下を書く。

```text
docs/agents/engineering-flow.md
docs/agents/issue-tracker.md
docs/agents/domain.md
```

書き込み直前に `git status --short` を再確認する。更新対象ファイルが modified / staged / untracked の場合は、既存変更を保持して merge するか中止するかをユーザーに確認する。

local markdown issue を選んだ場合、存在しなければ次も作る。

```text
docs/issues/SEQUENCE  # 初期値 0
docs/issues/closed/
```

`AGENTS.md` / `CLAUDE.md` には次の managed block を追加または更新する。
既存 marker がある場合だけ marker 内を置換する。marker がない場合はファイル末尾に追加する。周辺のユーザー記述は編集しない。

```md
<!-- BEGIN engineering-flow -->
## Engineering flow

This repository uses repo-local engineering flow settings.

- Flow rules: `docs/agents/engineering-flow.md`
- Issue tracker: `docs/agents/issue-tracker.md`
- Domain and design docs: `docs/agents/domain.md`

Before implementation, use a polished issue as the implementation design contract unless the flow explicitly allows skipping it.
<!-- END engineering-flow -->
```

### 5. Done

完了報告には次を含める。

- 作成・更新したファイル
- issue tracker の種類
- PRD / Design Doc の location
- local markdown issue の sequence 規則（該当時）
- 次に使うべき skill: `draft-issue` または `polish-issue`
