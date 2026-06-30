---
name: create-skill
description: agent skill の新規作成・既存 skill の draft 改善を行う。workflow / reference / diagnostic / rubric / wrapper の archetype、metadata discoverability、positive / negative trigger、配置、progressive disclosure、deterministic resources を決めて SKILL.md を書くが、品質判定や配布前 gate は review-diff-skill / review-skill に委譲する。
---

agent skill を、予測可能に動く小さな部品として draft する。
この skill は作成・改善の入口であり、レビューや配布判定は自分で完結しない。

## Workflow

1. 目的を確認する。
   - 何をできるようにする skill か。
   - いつ起動すべきか。
   - 期待する出力や完了条件は何か。
   - project 固有か、汎用 skill か。

2. skill archetype を決める。
   - workflow skill: TDD、PR 作成、レビューなど、agent に手順・停止条件・出力形式を踏ませる。
   - reference skill: CLI、API、ライブラリ、設定ファイルなどの利用者向けリファレンスとして、即答・操作支援・トラブルシュートを行う。
   - diagnostic skill: 既知の症状から確認コマンド、原因切り分け、対処へ進む。
   - rubric skill: レビュー観点や評価 protocol を他 skill から再利用できる形で提供する。
   - wrapper skill: 複数 skill、外部 command、repo 固有手順を組み合わせる入口にする。
   - 迷ったら、通常 path で agent に強制したいものが「手順」なら workflow、「知識の参照と選択」なら reference、「症状から分岐」なら diagnostic として扱う。

3. 起動方式を決める。
   - model-invoked: agent が自律的に発見すべき、または他 skill から使う可能性がある。
   - user-invoked: ユーザーが明示的に呼ぶだけでよい。`disable-model-invocation: true` を付ける。
   - 迷ったら、常時 context に載せる価値があるかで判断する。

4. 配置を決める。
   - 汎用 skill は `nananaman/skills` を source of truth にする。
   - project 固有 skill は対象 project の `.claude/skills/` などに置く。
   - 外部由来の内容を取り込む場合は、必要に応じて `NOTICE.md` を置く。

5. discoverability contract を先に固定する。
   - `name:` は skill ディレクトリ名と完全一致させる。
   - `name:` は小文字、数字、単一ハイフンだけで構成し、1〜64 文字に収める。
   - description は紹介文ではなく起動条件として書く。
   - description は agent が skill 読み込み前に見る唯一の routing 情報として扱う。
   - description には positive trigger と negative trigger を両方入れる。
   - description の各 trigger branch が本文 workflow の入口に対応するようにする。
   - reference skill では、対象 product / command / API、扱う質問種別、扱わない近接領域を description に入れる。
   - description は 1,024 文字以内に収め、可能なら三人称の capability 文として書く。

6. draft を書く。
   - `SKILL.md` は agent が実行する手順を中心に置く。
   - `SKILL.md` の本文には、agent の判断・手順・停止条件・出力形式を変える情報だけを置く。実行に効かない情報は、削除するか、PR body、commit message、review note などに分離する。
   - workflow / rubric / wrapper skill の `SKILL.md` は通常 500 行未満に保つ。超える場合は情報設計を見直す。
   - reference / diagnostic skill は、通常 path で参照する表、制限、頻出 recipe、確認コマンドを本文に置いてよい。ただし「読むだけで重い網羅資料」ではなく、agent が質問に答えるための地図と実用断片に絞る。
   - 長い説明・用語・網羅的な例・評価手順は `references/` や `GLOSSARY.md` に逃がす。
   - テンプレート、schema、静的素材は `assets/` に置き、必要になった時点で読む指示を書く。
   - 壊れやすい解析、繰り返し boilerplate、正規表現処理は tiny CLI として `scripts/` に置くことを検討する。
   - `scripts/` は stdout / stderr で agent が自己修正できる具体的な結果を返す設計にする。
   - `references/`、`assets/`、`scripts/` は原則 1 階層に保ち、本文中の path は forward slash の相対 path で書く。
   - README、CHANGELOG、INSTALLATION guide など人間向け文書は、agent の実行に必要でない限り skill 内に作らない。

7. reference / diagnostic skill では利用者向け runbook 構造を使う。
   - 冒頭で対象 tool / domain を 1〜2 文で説明する。
   - 利用者向けか、実装者向けか、運用者向けかを明示し、対象外を blockquote などで早めに書く。
   - 必要に応じて Requirements / Compatibility、Installation / Setup、Command map / API map、Common recipes、Options / Flags、Config files、Known limitations、Troubleshooting、Quick reference を置く。
   - destructive command、課金・本番影響・永続変更を伴う command には確認条件や注意を添える。
   - バージョン、OS、architecture、provider 差分で挙動が変わる情報は条件付きで書く。
   - 外部資料を元にする場合は、構成だけ借りるのか、内容も取り込むのかを分ける。内容を取り込む場合は upstream URL、取得日、license / attribution、更新時の確認方法を残す。
   - 古くなりやすい command reference には、可能なら `--help`、`version`、公式 docs などの確認手順を添える。

8. 自己点検してから止める。
   - skill ディレクトリ名と frontmatter の `name:` が一致しているか確認する。
   - description の各 trigger branch が本文の手順に対応しているか確認する。
   - negative trigger が過発火しやすい近接領域を明示しているか確認する。
   - skill archetype と本文構造が一致しているか確認する。
   - reference / diagnostic skill では、quick reference と詳細説明が矛盾していないか、destructive command の扱いが安全か確認する。
   - 通常 path を実行するために不要な参照ファイルを読ませていないか確認する。
   - 完了条件が agent に判定可能か確認する。
   - 勝手に commit / push / pin / install へ進む文言がないか確認する。

9. レビューへ渡す。
   - draft 作成後は `review-diff-skill` で差分レビューする。
   - skill 全体の責務・構造・発火条件を見直す場合は `review-skill` を使う。
   - `git commit`、push、APM pin 更新、`apm install -g` はこの skill では実行しない。

## Done Criteria

create-skill の完了は「レビュー可能な draft ができた」状態である。
次を満たしたら止めて、レビュー結果または次のレビュー手順をユーザーへ報告する。

- 目的、起動条件、negative trigger、期待出力が本文から読める。
- skill archetype が明確で、本文構造と一致している。
- 起動方式と配置が明確である。
- `name:` と配置ディレクトリが一致し、metadata が routing 情報として機能する。
- workflow / rubric / wrapper skill では、`SKILL.md` が手順中心で、参照情報・テンプレート・deterministic script と分離されている。
- reference / diagnostic skill では、対象 scope、利用者、条件差分、頻出 recipe、制限、troubleshooting、quick reference が agent の回答や操作支援に必要な粒度で整理されている。
- 通常 path で不要な context を読ませない progressive disclosure になっている。
- commit / push / pin / install を実行していない。
