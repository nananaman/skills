---
name: setup-engineering-flow
description: リポジトリごとのエンジニアリングフローを初期設定する。issue tracker、PRD、Design Doc、ADR、一時的な計画の配置、ローカル Markdown issue の採番、AGENTS.md や CLAUDE.md の参照ブロックを整える。task-breakdown の利用前、または create-plan の規則を継続運用として保存するときに、ユーザーの明示指示で実行する。通常のタスク分解、計画作成、実装、レビューでは使わない。
disable-model-invocation: true
---

# エンジニアリングフローの設定

`task-breakdown` が前提にし、`create-plan` が任意の追加情報として使うリポジトリ固有の設定を作る。
これは一度だけ実行する対話駆動の skill であり、決定的に動くスクリプトではない。

## 目的

次をリポジトリごとの source of truth として記録する。

- issue tracker：GitHub Issue、ローカル Markdown、その他
- PRD / Design Doc / ADR の置き場所
- 一時的な計画の置き場所
- エンジニアリングフロー：PRD、Design Doc、ADR → タスク分解 → issue → 計画作成 → 実装 → 検証 → simplify-code → レビュー → 計画の完了処理
- ローカル Markdown issue の採番規則
- エージェントが読む `AGENTS.md` または `CLAUDE.md` の参照ブロック

## 原則

- 質問は一度に一つだけ行う。
- 既存運用を探索してから提案する。存在する `docs/`, `issues/`, `.github/`, `AGENTS.md`, `CLAUDE.md` を無視しない。
- ユーザーに用語を説明してから選択肢を出す。
- draft を提示して確認してから書く。
- 既存 `AGENTS.md` / `CLAUDE.md` を全面 rewrite しない。
- managed block marker がある場合だけ marker 内を置換する。marker がなければ末尾に追加し、周辺本文は触らない。
- 書き込み対象ファイルに未 commit の変更がある場合は、merge 方針を確認するまで書かない。
- commit / push / APM pin / install は行わない。

## 手順

### 1. 現状を調査する

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

### 2. 調査結果を示す

存在するもの・存在しないものを短く報告する。
次の判断を一つずつ確認する。

#### A. Issue tracker

説明: issue tracker は実装作業単位を管理する場所である。
`task-breakdown` はここを読んで task を作成する。
`create-plan` はここを読んで対象 issue を取得する。

選択肢:

- GitHub Issue：`gh` CLI で issue を作成または更新する
- ローカル Markdown：リポジトリ内の Markdown ファイルとして管理する
- その他：Jira や Linear など。ユーザーの説明を文章で記録する

GitHub remote がある場合は GitHub を提案する。
`docs/issues/` または `issues/` がある場合は local markdown も有力候補として示す。

#### B. PRD / Design Doc / ADR location

説明: PRD は「なぜ・何を・どこまで」を固定する文書で、Design Doc / ADR は複数 task や将来から参照する設計判断を固定する文書である。
Design Doc には必要に応じて Glossary / Domain Model を含める。

デフォルト:

```text
docs/prd/
docs/design/
docs/adr/
```

ただし GitHub Issue / Discussion / Wiki / other location も許可する。

#### C. 一時的な計画の保存場所

説明：計画は担当者が issue を取得した後に作る、一度も commit しない一時的な実装設計の契約である。
デフォルト:

```text
plans/
```

計画ディレクトリは `.gitignore` に追加しない。
既存の計画ディレクトリやプロジェクト規則がある場合は、それを使うか確認する。

#### D. ローカル Markdown issue の規則

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

#### E. AGENTS.md / CLAUDE.md update

説明：リポジトリ固有の規則をエージェントが毎回発見できるように、`AGENTS.md` または `CLAUDE.md` に参照ブロックを置く。

選択規則:

- `CLAUDE.md` があればそれを更新する
- なければ `AGENTS.md` を更新する
- 両方なければ、どちらを作るか質問する

### 3. ファイルの草案を作る

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

### 4. ファイルを保存する

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
## エンジニアリングフロー

このリポジトリでは、リポジトリ固有のエンジニアリングフロー設定を使用する。

- フロー規則：`docs/agents/engineering-flow.md`
- Issue tracker：`docs/agents/issue-tracker.md`
- ドメイン文書と設計文書：`docs/agents/domain.md`

タスクを取得したら、このフローに従って一時的な実装計画を作成する。計画ファイルは commit せず、内容を指定された commit message に保存し、実装レビュー後に削除する。
<!-- END engineering-flow -->
```

### 5. 完了を報告する

完了報告には次を含める。

- 作成・更新したファイル
- issue tracker の種類
- PRD / Design Doc / ADR の location
- temporary plan の location
- local markdown issue の sequence 規則（該当時）
- 次に使うべき skill: `task-breakdown` または `create-plan`
