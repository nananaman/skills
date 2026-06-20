---
name: skill-creator
description: agent skill を作成・改善・評価する。新しい skill を作る、既存 skill を直す、trigger description を設計する、APM で配布できる形に整理する、または skill の品質をレビューするときに使う。
---

agent skill を、予測可能に動く小さな部品として作成・改善する。

## 進め方

1. 目的を確認する。
   - 何をできるようにする skill か。
   - いつ起動すべきか。
   - 期待する出力や完了条件は何か。
   - project 固有か、汎用 skill か。

2. 起動方式を決める。
   - model-invoked: agent が自律的に発見すべき、または他 skill から使う可能性がある。
   - user-invoked: ユーザーが明示的に呼ぶだけでよい。`disable-model-invocation: true` を付ける。
   - 迷ったら、常時 context に載せる価値があるかで判断する。

3. draft を書く。
   - `SKILL.md` は手順を中心に置く。
   - 長い説明・用語・例・評価手順は `references/` や `GLOSSARY.md` に逃がす。
   - description は「何をするか」と「どの branch で起動するか」を短く強く書く。

4. 品質チェックを通す。
   - `references/writing-great-skills.md` を品質基準として参照する。
   - 特に predictability、description、information hierarchy、pruning、failure modes を確認する。

5. 必要なら評価する。
   - 客観的に判定できる skill なら eval prompt を作る。
   - with-skill / baseline を比較する。
   - 主観評価が中心の skill は、代表的な利用例をユーザーに確認してもらう。
   - 詳細は `references/evals.md` を読む。

6. 配布形に整える。
   - skill ディレクトリ名と frontmatter の `name:` を一致させる。
   - `README.md` に追加する。
   - APM で参照できるように commit し、full SHA で pin する。

## 配置方針

- 汎用 skill は `nananaman/skills` を source of truth にする。
- project 固有 skill は対象 project の `.claude/skills/` などに置く。
- 外部由来の内容を取り込む場合は、必要に応じて `NOTICE.md` を置く。

## 完了条件

skill が次を満たしたら完了する。

- 起動方式が明確である。
- description が短く、distinct branch を表している。
- 手順・参照・用語が適切に分離されている。
- no-op、duplication、sediment、sprawl が目立たない。
- APM で管理できる配置になっている。
