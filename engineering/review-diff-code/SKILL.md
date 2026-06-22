---
name: review-diff-code
description: 現在の diff、branch diff、commit diff、PR base に対する branch diff を、5つの観点から並列に厳しめレビューする。コードレビュー、PR レビュー、別モデルレビュー、保守性レビュー、実装後の closeout review で使う。リポジトリ全体監査、設計相談、テスト作成、通常実装、修正だけの依頼では使わない。
---

# Review Diff Code

現在の変更差分を、厳しめだがコストを抑えてレビューする。対象は diff であり、リポジトリ全体の一般監査ではない。

helper は 1 round の read-only review runner である。5つの観点別 reviewer を同じ engine / model で並列実行し、perspective ごとの structured findings と実行 summary を返す。finding の統合、採否判断、修正、再レビュー round 管理は本体 agent が行う。

## Workflow

1. レビュー対象を決める。
   - ユーザーが mode / base / commit / engine / model / thinking を指定したら、それを優先する。
   - dirty worktree があれば `--mode local` を使う。
   - open PR があれば PR の実 base を使う。
   - それ以外は branch diff を `origin/main` 基準で見る。
2. helper を read-only reviewer として実行する。
   - helper 実行中に作業ツリーを変更しない。
   - review のためだけに formatter / test / generation command を実行しない。format が必要なら、ユーザーの明示許可を得て review 前の別作業として行う。
3. helper summary を確認する。
   - `overall_status: success` なら全 perspective が成功している。
   - `overall_status: partial_failure` なら成功した perspective の finding は使い、失敗した perspective を最終報告に明示する。
   - 全 perspective が失敗した場合はレビュー不能として停止し、理由を報告する。
4. perspective ごとの finding を読む。
   - 重複 finding は同一 issue として束ねる。
   - ただし、観点ごとの根拠や severity 差は捨てない。
5. 各 issue を批判的に検証する。
   - 対象コードと周辺コードを直接読む。
   - 外部 library の挙動に依存する finding は docs / source / types を確認する。
   - diff、既存コード、documented behavior で根拠が確認できるものだけ accepted にする。
6. accepted finding だけを修正する。
   - 修正は最小限にし、正しい ownership boundary に置く。
7. 修正した場合は focused test / proof を実行する。
8. accepted finding を修正した場合は、必ず helper を再実行する。
   - 再レビューも毎回全5 perspective で行う。
   - accepted finding がなくなったら終了する。
   - 最大5 round まで行う。
   - 5 round 後も accepted finding が残る、または新規 finding が出続ける場合は停止し、残件と判断理由をユーザーに報告する。
9. 最終報告では、実行コマンド、engine / model、round summary、tests / proof、accepted / rejected finding、clean result を明示する。

## Perspectives

helper は次の5観点を英語 prompt で並列実行する。

1. `Correctness / Regression`
   - runtime path、境界条件、順序、migration、状態不整合、既存 invariant との矛盾を見る。
2. `Security / Safety`
   - secret exposure、authn/authz、permission boundary、injection、危険な file/network/process access、安全 check の削除を見る。
3. `Maintainability / Structure`
   - 責務境界、layer / module 配置、局所例外、hidden coupling、orchestration の読みづらさを見る。
4. `Simplification / Code Judo`
   - 不要な branch / helper / wrapper / generic mechanism、重複 concept、AI 生成的な過剰複雑性、振る舞いを保った削除余地を見る。
5. `Type / API / Contract`
   - cast、`any` / `unknown`、optionality、nullability、schema / API 互換性、public contract、serialization、documented behavior との不一致を見る。

各 reviewer は担当観点に注目する。別観点の指摘を禁止する必要はないが、finding は high-confidence かつ action 可能なものに絞る。

## Accepted / Rejected Criteria

### Accepted

次を満たす finding だけ accepted にする。

- 今回の diff が具体的な bug、security risk、regression risk、contract break、または保守上の明確な risk を作っている。
- diff、周辺コード、既存 invariant、documented behavior、types / schema / API contract のいずれかで根拠を確認できる。
- 最小修正で risk を下げられる。
- 修正先の ownership boundary が明確である。

### Rejected

次の finding は rejected にする。

- cosmetic nit、style preference、命名や配置の好みだけの指摘。
- speculative risk で、実際に壊れる path や contract との矛盾が確認できないもの。
- 今回の diff と無関係な既存問題。
- broad rewrite、過剰設計、または修正 risk が問題の risk に見合わないもの。
- 既存の記述、型、テスト、documented behavior で既に包含されているもの。
- evidence が不足し、追加調査でも根拠を確認できないもの。

既存問題は原則 rejected とする。ただし今回の diff がその問題を悪化させた、露出させた、依存した、または安全策を削った場合だけ accepted にする。

`[low]` finding も reviewer は出してよい。後続の本体 agent が妥当性と対応要否を判断する。

## Contract

- correctness、regression risk、security、maintainability を必ず見る。
- 構造品質にも高い基準を適用する。
- finding は high-confidence かつ action 可能なものだけに絞る。
- 修正は最小限にし、正しい ownership boundary に置く。
- security finding は、変更が具体的で action 可能な risk を作った場合、または重要な safety check を消した場合だけ accepted にする。
- review のためだけに push しない。push はユーザーが依頼した場合だけ行う。
- built-in `codex review`、nested reviewer、reviewer panel を review 中から起動しない。helper が 1 つの bundle を作り、5つの perspective prompt を 1 つの selected engine / model に渡す。

## 推奨コマンド

同梱 helper を使う。helper は既定で5観点並列 review を実行する。

Claude Code 側に展開されている場合:

```bash
~/.claude/skills/review-diff-code/scripts/review-diff-code --mode branch --base origin/main
```

agent-skills 側に展開されている場合:

```bash
~/.agents/skills/review-diff-code/scripts/review-diff-code --mode branch --base origin/main
```

open PR がある場合は、PR の実 base を使う。

```bash
base=$(gh pr view --json baseRefName --jq .baseRefName)
~/.agents/skills/review-diff-code/scripts/review-diff-code --mode branch --base "origin/$base"
```

未 commit の local work をレビューする。

```bash
~/.agents/skills/review-diff-code/scripts/review-diff-code --mode local
```

単一 commit をレビューする。

```bash
~/.agents/skills/review-diff-code/scripts/review-diff-code --mode commit --commit HEAD
```

engine / model / thinking / timeout を明示する。

```bash
~/.agents/skills/review-diff-code/scripts/review-diff-code --engine pi --mode branch --base origin/main
~/.agents/skills/review-diff-code/scripts/review-diff-code --engine codex --model gpt-5.4 --thinking high --mode branch --base origin/main
~/.agents/skills/review-diff-code/scripts/review-diff-code --timeout-sec 900 --mode branch --base origin/main
```

## Engine / Model Override

通常は helper の既定を使う。ユーザーが engine / model / thinking / timeout を指定した場合だけ override する。`--engine auto` は利用可能な engine を `pi`、`codex`、`claude` の順に選ぶ。`pi` では model を固定しない。

```bash
REVIEW_DIFF_CODE_ENGINE=auto
REVIEW_DIFF_CODE_TIMEOUT_SEC=600
REVIEW_DIFF_CODE_PI_MODEL=<optional>
REVIEW_DIFF_CODE_PI_THINKING=low
REVIEW_DIFF_CODE_CODEX_MODEL=gpt-5.4-mini
REVIEW_DIFF_CODE_CODEX_THINKING=low
REVIEW_DIFF_CODE_CLAUDE_MODEL=sonnet
```

engine ごとの read-only 境界:

- `pi`: `--no-session --tools read,grep,find,ls` で実行する。
- `codex`: `exec --ephemeral -s read-only` で実行する。
- `claude`: `--print --no-session-persistence` と prompt-level read-only contract で実行する。

## Helper Output

helper は summary、perspective ごとの findings、diagnostics を出す。

```md
# Review Summary

overall_status: success / partial_failure / failed
engine: pi
model: default
thinking: low
timeout_sec: 600
mode: branch
prompt_file: none

| Perspective | Status |
| --- | --- |
| Correctness / Regression | success |
| Security / Safety | success |
| Maintainability / Structure | success |
| Simplification / Code Judo | success |
| Type / API / Contract | success |

# Findings by Perspective

## Correctness / Regression

status: success

No actionable findings.
```

一部 perspective が timeout / failed でも、成功した perspective が1つ以上あれば exit 0 で `overall_status: partial_failure` を返す。全 perspective が失敗した場合だけ non-zero exit とする。

## Reviewer Finding Format

reviewer は英語で findings だけを出す。総評、前置き、実行ログ、checklist は出さない。

```md
## Findings

### [critical|high|medium|low] title
- Target: path:line
- Problem: what breaks or what becomes harder to maintain
- Evidence: facts from the diff, existing code, or documented behavior
- Suggested fix: the smallest appropriate fix at the right ownership boundary
```

finding がない場合は次の文字列に統一する。

```text
No actionable findings.
```

## Closeout Report

ユーザーへの報告には以下を含める。

- 実行した review command。
- 使用した engine と model。
- 各 round の summary。
  - 例: `Round 1: accepted 2 / rejected 5 / fixed 2 / all perspectives succeeded`
  - 例: `Round 2: accepted 0 / rejected 1 / clean after fix`
- partial failure があった場合、失敗した perspective と扱い。
- 実行した tests / proof。
- 採用または却下した finding と、その簡単な理由。
- clean review result、または残った finding を意識的に却下した理由。
