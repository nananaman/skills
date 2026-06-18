---
name: code-review
description: 現在の diff、branch、commit、PR に対して、厳しめかつコストを抑えたコードレビューを実行する。コードレビュー、PR レビュー、autoreview、別モデルレビューを依頼されたときに使う。
---

# Code Review

現在の変更に対して、厳しめだがコストを抑えたレビューを行う。この skill は常に correctness、security、maintainability を確認する。さらに、構造品質にも高い基準を適用する: スパゲッティ化、抽象化の質、ファイルサイズ肥大、責務境界、振る舞いを変えずに大きく単純化できる余地を見る。

## デフォルト動作

- コストを抑えるため、まず軽量レビュー用モデルを優先する。
- `pi` が利用できる場合は `opencode-go/deepseek-v4-flash` を優先する。
- Claude Code 経由では `sonnet` を使う。
- Codex 経由では mini / spark 系の coding model を使う。
- 高価なモデルへの escalation は、ユーザーが明示した場合、または軽量モデルでは十分に評価できない場合だけ行う。
- レビュー結果は助言として扱う。修正を採用する前に、必ず該当コードを読んで妥当性を確認する。
- 高信頼で action 可能な finding だけを報告する。cosmetic nit、好みの問題、推測ベースのリスクは報告しない。

出力言語はこの skill では固定しない。active な global agent instructions に従う。

## 推奨コマンド

同梱 helper を使う。

Claude Code 側に展開されている場合:

```bash
~/.claude/skills/code-review/scripts/code-review --mode branch --base origin/main
```

agent-skills 側に展開されている場合:

```bash
~/.agents/skills/code-review/scripts/code-review --mode branch --base origin/main
```

branch に open PR がある場合は、PR の実 base を使う。

```bash
base=$(gh pr view --json baseRefName --jq .baseRefName)
~/.claude/skills/code-review/scripts/code-review --mode branch --base "origin/$base"
```

未 commit の local work をレビューする。

```bash
~/.claude/skills/code-review/scripts/code-review --mode local
```

単一 commit をレビューする。

```bash
~/.claude/skills/code-review/scripts/code-review --mode commit --commit HEAD
```

engine を明示する。

```bash
~/.claude/skills/code-review/scripts/code-review --engine pi --mode branch --base origin/main
~/.claude/skills/code-review/scripts/code-review --engine claude --mode branch --base origin/main
~/.claude/skills/code-review/scripts/code-review --engine codex --mode branch --base origin/main
```

## Model Policy

デフォルトは意図的に軽量モデルにする。

| engine | default model | notes |
| --- | --- | --- |
| `pi` | `opencode-go/deepseek-v4-flash` | 第一候補。デフォルトで low thinking。 |
| `claude` | `sonnet` | Claude Code CLI が利用できる場合に使う。 |
| `codex` | `gpt-5.4-mini` | local Codex が別の軽量モデル名を公開している場合は `CODE_REVIEW_CODEX_MODEL` で上書きする。 |

環境変数 override:

```bash
CODE_REVIEW_ENGINE=pi
CODE_REVIEW_PI_MODEL=opencode-go/deepseek-v4-flash
CODE_REVIEW_PI_THINKING=low
CODE_REVIEW_CLAUDE_MODEL=sonnet
CODE_REVIEW_CODEX_MODEL=gpt-5.4-mini
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
