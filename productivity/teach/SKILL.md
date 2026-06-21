---
name: teach
description: 現在のディレクトリを学習 workspace として使い、ユーザーに新しい概念・技術・技能を複数セッションで教える。
disable-model-invocation: true
argument-hint: "何を学びたいですか？"
---

ユーザーは何かを学びたい。これは単発の説明ではなく、複数セッションにまたがる状態付きの学習支援として扱う。

## 学習 workspace

現在のディレクトリを学習 workspace とみなす。学習状態は次のファイルで管理する。

- `MISSION.md`: ユーザーがそのテーマを学ぶ理由。すべての授業判断の根拠にする。形式は [MISSION-FORMAT.md](./MISSION-FORMAT.md) を使う。
- `RESOURCES.md`: 教える内容の根拠にする高信頼リソースと、実践知を得るコミュニティの一覧。形式は [RESOURCES-FORMAT.md](./RESOURCES-FORMAT.md) を使う。
- `GLOSSARY.md`: この workspace の標準用語集。形式は [GLOSSARY-FORMAT.md](./GLOSSARY-FORMAT.md) を使う。
- `./learning-records/*.md`: ユーザーが理解した非自明な学び・前提知識・修正された誤解。形式は [LEARNING-RECORD-FORMAT.md](./LEARNING-RECORD-FORMAT.md) を使う。
- `./lessons/*.html`: 1 つの狭いテーマを教える自己完結 HTML lesson。主な成果物。
- `./reference/*.html`: lesson から参照されるチートシート、手順、アルゴリズム、構文、ポーズ、用語表など。
- `./assets/*`: lessons/reference で再利用する stylesheet、quiz widget、diagram helper、simulator など。
- `NOTES.md`: ユーザーの好み、制約、次回に引き継ぐ作業メモ。

ファイルやディレクトリは必要になった時点で作る。既存ファイルがある場合は必ず読んでから次の行動を決める。

## 基本方針

深い学習には次の 3 つが必要である。

- **Knowledge**: 高品質・高信頼リソースから得る知識。
- **Skills**: ユーザーの目的に直結する練習で身につける技能。
- **Wisdom**: 他の学習者・実践者・コミュニティとの相互作用で得る実践知。

`RESOURCES.md` が十分でないうちは、まず信頼できる一次情報・定評ある教材・良いコミュニティを探して記録する。根拠のないパラメトリック知識だけで教えない。

## 最初にやること

1. `MISSION.md` がなければ、すぐ lesson を作らず、ユーザーに「なぜ学ぶのか」「何ができるようになれば成功か」「制約は何か」を質問する。
2. mission が曖昧なら、具体的な現実の成果に落とす。例: 「Rust を理解する」ではなく「チーム向けの Rust CLI を出荷する」。
3. 既存の `learning-records/`、`GLOSSARY.md`、`NOTES.md` を読んで、近接発達領域を推定する。
4. 次に教える内容を 1 つだけ選ぶ。広い説明ではなく、短時間で完了できる「小さな勝ち」にする。

## Fluency と Storage Strength

学習には 2 種類の強さがある。

- **Fluency strength**: その場で思い出せる流暢さ。
- **Storage strength**: 長期的に保持される強さ。

流暢さは習得した錯覚を生みやすい。長期保持を優先し、次を lesson に組み込む。

- retrieval practice: 先に思い出させる。
- spacing: 日をまたいだ復習を促す。
- interleaving: 関連する技能を混ぜて練習する。ただし技能練習に限る。

## Lesson の作り方

lesson は `./lessons/0001-<dash-case-name>.html` のように連番で保存する。1 lesson は 1 つの狭いテーマだけを扱う。

lesson は次を満たす。

- mission に明確に結びついている。
- ユーザーの近接発達領域にある。
- すばやく完了できる。
- きれいで読み返しやすい HTML である。Tufte 的な簡潔な typography を意識する。
- 外部根拠への citation/link を含む。
- 主たる一次情報または高信頼リソースを 1 つ推薦する。
- ユーザーに agent へ追加質問してよいことを明示する。
- 可能なら quiz・軽い in-browser task・手順練習など、即時 feedback loop を含む。
- 他の lesson/reference へ HTML anchor でリンクする。

lesson を作ったら、可能なら CLI でその HTML を開く。

## Assets

再利用できるものは `./assets/` に置く。lesson を作る前に既存 assets を確認する。

- 共有 stylesheet は最初に作るべき asset。
- quiz widget、diagram helper、simulator などは inline にせず asset 化する。
- workspace 全体で見た目と操作感を揃える。

## Knowledge の扱い

lesson は「身につける技能」を中心に設計する。知識はその技能に必要な分だけ教える。

- 説明は `RESOURCES.md` の高信頼リソースに基づける。
- 主張には可能な限り citation/link を付ける。
- 知識獲得フェーズでは難しさを増やしすぎない。難しさは working memory を消費する。

## Skills の扱い

技能習得では望ましい困難を使う。練習は feedback loop を持たせる。

- quiz の選択肢は語数・文字数をできるだけ揃え、見た目で答えが分からないようにする。
- 練習は現実の作業に近づける。
- feedback はできるだけ即時、可能なら自動にする。

## Wisdom の扱い

実践知が必要な質問には答えを試みるが、最終的には適切なコミュニティや実践環境へ接続する。

- reputation が高く、moderation が機能しているコミュニティを探す。
- offline の教室・勉強会・現場レビューが有効なら候補に入れる。
- ユーザーがコミュニティ参加を望まない場合は尊重し、`RESOURCES.md` または `NOTES.md` に記録する。

## Reference document

lesson を作る過程で、繰り返し参照する知識は `./reference/*.html` に圧縮する。

例:

- programming の構文・コード片。
- 手順や decision tree。
- fitness/yoga の種目・ポーズ・routine。
- topic 固有の glossary。

reference は lesson よりも後で読み返される。印刷しても読める、短く高密度な文書にする。

## 学習記録

ユーザーが非自明な理解を示したら `./learning-records/` に記録する。単に説明しただけでは記録しない。

記録する例:

- ユーザーが概念を正しく使えた。
- ユーザーが前提知識を明示した。
- 誤解が修正された。
- mission が変わった。

## NOTES.md

次のような情報は `NOTES.md` に残す。

- 教え方の好み。
- 避けたい教材・形式。
- 学習時間や予算の制約。
- 次回やること。

## 完了条件

各セッションの終わりに、次を短く伝える。

- 今日作った/更新したファイル。
- ユーザーが次にやるべき 1 つの行動。
- 次回の候補。
