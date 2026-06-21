---
name: create-skill
description: agent skill の新規作成・既存 skill の draft 改善を行う。目的、起動条件、配置、最小構成を決めて SKILL.md を書くが、品質判定や配布前 gate は review-diff-skill / review-skill に委譲する。
---

agent skill を、予測可能に動く小さな部品として draft する。
この skill は作成・改善の入口であり、レビューや配布判定は自分で完結しない。

## Workflow

1. 目的を確認する。
   - 何をできるようにする skill か。
   - いつ起動すべきか。
   - 期待する出力や完了条件は何か。
   - project 固有か、汎用 skill か。

2. 起動方式を決める。
   - model-invoked: agent が自律的に発見すべき、または他 skill から使う可能性がある。
   - user-invoked: ユーザーが明示的に呼ぶだけでよい。`disable-model-invocation: true` を付ける。
   - 迷ったら、常時 context に載せる価値があるかで判断する。

3. 配置を決める。
   - 汎用 skill は `nananaman/skills` を source of truth にする。
   - project 固有 skill は対象 project の `.claude/skills/` などに置く。
   - 外部由来の内容を取り込む場合は、必要に応じて `NOTICE.md` を置く。

4. draft を書く。
   - `SKILL.md` は agent が実行する手順を中心に置く。
   - 長い説明・用語・例・評価手順は `references/` や `GLOSSARY.md` に逃がす。
   - description は紹介文ではなく起動条件として書く。
   - description は「何をするか」と「どの branch で起動するか」を短く強く書く。

5. 自己点検してから止める。
   - skill ディレクトリ名と frontmatter の `name:` が一致しているか確認する。
   - description の各 trigger branch が本文の手順に対応しているか確認する。
   - 完了条件が agent に判定可能か確認する。
   - 勝手に commit / push / pin / install へ進む文言がないか確認する。

6. レビューへ渡す。
   - draft 作成後は `review-diff-skill` で差分レビューする。
   - skill 全体の責務・構造・発火条件を見直す場合は `review-skill` を使う。
   - `git commit`、push、APM pin 更新、`apm install -g` はこの skill では実行しない。

## Done Criteria

create-skill の完了は「レビュー可能な draft ができた」状態である。
次を満たしたら止めて、レビュー結果または次のレビュー手順をユーザーへ報告する。

- 目的、起動条件、期待出力が本文から読める。
- 起動方式と配置が明確である。
- `SKILL.md` が手順中心で、参照情報と分離されている。
- commit / push / pin / install を実行していない。
