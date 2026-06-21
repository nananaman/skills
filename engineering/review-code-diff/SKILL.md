---
name: review-code-diff
description: 現在の diff、branch diff、commit diff、PR diff を対象に、Codex を既定 reviewer として correctness・security・maintainability・構造品質を厳しめにレビューする。コードレビュー、PR レビュー、別モデルレビュー、保守性レビュー、実装後の closeout review を依頼されたときに使う。
---

# Review Code Diff

現在の変更差分を、厳しめだがコストを抑えてレビューする。対象は diff であり、リポジトリ全体の一般監査ではない。

## Workflow

1. レビュー対象を決める。
   - ユーザーが mode / base / commit / engine / model を指定したら、それを優先する。
   - dirty worktree があれば `--mode local` を使う。
   - open PR があれば PR の実 base を使う。
   - それ以外は branch diff を `origin/main` 基準で見る。
2. helper を read-only reviewer として実行する。
   - 既定 engine は Codex。
   - 実行環境依存の private engine は既定にしない。
   - formatter が行番号を変える可能性がある場合は、先に format してからレビューする。
3. reviewer の finding をそのまま採用しない。
   - 各 finding について、対象コードと周辺コードを直接読む。
   - 外部 library の挙動に依存する finding は docs / source / types を確認する。
   - diff、既存コード、documented behavior で根拠が確認できるものだけ accepted にする。
   - speculative risk、cosmetic nit、好み、過剰な rewrite は rejected にする。
4. accepted finding を直した場合は、focused test / proof を実行し、必要なら再レビューする。
5. 最終報告では、実行コマンド、engine / model、tests / proof、accepted / rejected finding、clean result を明示する。

## Contract

- correctness、regression risk、security、maintainability を必ず見る。
- 構造品質にも高い基準を適用する。
- finding は high-confidence かつ action 可能なものだけに絞る。
- 修正は最小限にし、正しい ownership boundary に置く。
- security finding は、変更が具体的で action 可能な risk を作った場合、または重要な safety check を消した場合だけ報告する。
- review のためだけに push しない。push はユーザーが依頼した場合だけ行う。
- built-in `codex review`、nested reviewer、reviewer panel を review 中から起動しない。helper が 1 つの bundle を作り、1 つの selected engine に渡す。

## 推奨コマンド

同梱 helper を使う。

Claude Code 側に展開されている場合:

```bash
~/.claude/skills/review-code-diff/scripts/review-code-diff --mode branch --base origin/main
```

agent-skills 側に展開されている場合:

```bash
~/.agents/skills/review-code-diff/scripts/review-code-diff --mode branch --base origin/main
```

open PR がある場合は、PR の実 base を使う。

```bash
base=$(gh pr view --json baseRefName --jq .baseRefName)
~/.agents/skills/review-code-diff/scripts/review-code-diff --mode branch --base "origin/$base"
```

未 commit の local work をレビューする。

```bash
~/.agents/skills/review-code-diff/scripts/review-code-diff --mode local
```

単一 commit をレビューする。

```bash
~/.agents/skills/review-code-diff/scripts/review-code-diff --mode commit --commit HEAD
```

engine / model を明示する。

```bash
~/.agents/skills/review-code-diff/scripts/review-code-diff --engine codex --mode branch --base origin/main
~/.agents/skills/review-code-diff/scripts/review-code-diff --engine claude --mode branch --base origin/main
~/.agents/skills/review-code-diff/scripts/review-code-diff --engine codex --model gpt-5.4 --thinking high --mode branch --base origin/main
```

## Model Policy

既定は Codex。Codex が使えない場合だけ Claude に fallback する。

| engine | default model | notes |
| --- | --- | --- |
| `codex` | `gpt-5.4-mini` | default。local Codex が別の model 名を公開している場合は `REVIEW_CODE_DIFF_CODEX_MODEL` で上書きする。 |
| `claude` | `sonnet` | Claude Code CLI が利用できる場合の fallback。 |

環境変数 override:

```bash
REVIEW_CODE_DIFF_ENGINE=codex
REVIEW_CODE_DIFF_CODEX_MODEL=gpt-5.4-mini
REVIEW_CODE_DIFF_CODEX_THINKING=low
REVIEW_CODE_DIFF_CLAUDE_MODEL=sonnet
```

## 常時適用する厳格レビュー観点

以下は毎回必ず確認する。

- correctness regression、壊れた runtime path、migration / order mistake。
- security regression、secret exposure、permission boundary の破壊。
- 構造的な code-quality regression。
- スパゲッティ化: ad-hoc conditional、special-case branch、既存 flow への局所例外の継ぎ足し。
- 抽象化の質: thin wrapper、不要な indirection、魔法のような generic mechanism。
- Code judo: 振る舞いを保ったまま concept、branch、helper layer、偶発的複雑性を削れる余地。
- 責務境界: logic が正しい layer、package、module、helper に置かれているか。
- 型境界: cast、optionality、`any`、`unknown` が本来の invariant を隠していないか。
- ファイルサイズと分割: 特に 1000 行超えに近づく、または超える変更。
- orchestration quality: 避けられる逐次処理、非 atomic update、reasoning を難しくする流れ。

## 出力期待値

finding がある場合は、できるだけ次の形にする。

```md
## Findings

### [severity] title
- Target: path:line
- Problem: 何が壊れるか、または何が保守しづらくなるか
- Evidence: diff、既存コード、documented behavior からの根拠
- Suggested fix: 適切な責務境界での最小修正
```

action 可能な finding がない場合は、accepted / actionable finding がないことを active な agent instructions の言語で明示する。

## Closeout Report

ユーザーへの報告には以下を含める。

- 実行した review command。
- 使用した engine と model。
- 実行した tests / proof。
- 採用または却下した finding と、その簡単な理由。
- clean review result、または残った finding を意識的に却下した理由。

## Attribution

この local skill は以下から着想を得ている。

- `openclaw/agent-skills` の `autoreview` workflow ideas, MIT License。
- `cursor/plugins` の `cursor-team-kit/skills/thermo-nuclear-code-quality-review` review rubric ideas, MIT License。

詳細はこの skill directory の `NOTICE.md` と `LICENSE` を参照。
