---
name: explain-diff
description: 実装意図を保持するセッションから、ステージ済み、未ステージ、未追跡を含むローカル差分を変更前後と因果順で解説し、人間が確認とコメントを行う自己完結 HTML を生成するときに明示的に使う。コード品質レビュー、指摘生成、修正、branch、commit、PR の差分には使わない。
disable-model-invocation: true
---

# 差分の解説

現在のlocal差分を「なぜ必要か」「何が可能になるか」「各変更がどの順で成立させるか」という物語として人間へ説明する。
各説明は変更前と変更後を対比し、根拠となるhunkへ掘り下げられる形にする。
このskillは品質判定を行わない。コードレビューが必要なら `review-diff-code` を別に使う。

## 前提条件

- 実装した同一セッション、または実装意図を含むhandoffを受けたセッションで使う。
- 実装意図がなければ、差分から理由を推測せず、planまたはhandoffを求めて停止する。
- 対象は現在のGit repositoryにあるstaged、unstaged、untrackedのlocal差分だけ。

## 手順

1. frontend依存を準備する。

   初回または `node_modules` がない場合だけ、lockfileで固定された依存を導入する。

   ```sh
   npm ci --ignore-scripts --prefix <skill-directory>
   ```

   `node_modules` はrepositoryの `.gitignore` 対象であり、snapshotへ含めない。

2. snapshotを作る。

   ```sh
   python3 <skill-directory>/scripts/explain-diff.py snapshot
   ```

   stdoutの `snapshot.json` pathを保持する。差分がなければ停止する。

3. snapshotの `hunks` と実装意図から、変更前の問題と変更後の到達状態を定める。
   利用者・外部system・entry pointから観測できる変更を先頭に置き、そこから呼び出し先・依存先・内部表現へ読み下せる順に、同じ役割へ従属するhunkをまとめる。
   [`references/manifest-contract.md`](./references/manifest-contract.md) に従って、snapshotと同じdirectoryへ `manifest.json` を作る。
   renameと追従import修正のような機械的変更も、同じ目的なら一groupにする。
   groupごとに変更前、変更後、この形を選んだ理由、説明とdiffの対応を確かめる観点を書く。
   groupが後続groupに依存する場合は `depends_on` で理解経路を示す。
   riskやfile数、実装を成立させた作業順では並べ替えず、読み手が入口から依存先へ変更を追える順序を保つ。
   変更後のcomponent境界、処理flow、データflow、状態遷移を文章より明瞭に説明できる場合はMermaidの `diagrams` を作る。
   flowchartのnodeは役割が分かる名称と説明を持たせ、`node_links` でgroup・hunk・用語へ結び付ける。
   実装順やgroup順、importやfile一覧を並べただけになる場合は省略する。
   repository固有の名称、新しい概念、略語が解説や図に登場する場合は `glossary` で、この変更における意味を定義する。
   実装意図とhunkを明瞭に対応付けられない場合は推測で埋めず停止する。

4. reportを生成する。

   ```sh
   python3 <skill-directory>/scripts/explain-diff.py render \
     --snapshot <snapshot.json> \
     --manifest <manifest.json> \
     --output <snapshot-directory>/report.html \
     --no-open
   ```

   CLIが全hunkの一意な割当とmanifest contractを検証し、変更対象file一覧をsnapshotから決定的に表示する。
   validation errorはmanifestを直して再実行する。
   `stale snapshot` はlocal差分が変わった証拠なので、古いmanifestを流用せずStep 2からやり直す。

5. reportの対象、group数、fingerprint、生成pathを伝える。
   ローカルブラウザで開かず、生成済みレポートの配信を常に `host-artifact` skill へ委譲する。
   レポートはローカル差分全文を含むことを委譲先へ伝え、`host-artifact` の安全境界と自動転送方式の選択に従う。
   `host-artifact` が配信対象外と判断した場合、または配信に失敗した場合も生成済みレポートを削除せず、絶対パスを代替手段として伝える。

6. 人間の確認とコメントを待って停止する。
   reportのcheckboxは確認状態であり、承認や品質gateではない。

7. ユーザーがreportからfeedback Markdownを貼ったら、修正へ進む前にfingerprintを照合する。

   ```sh
   python3 <skill-directory>/scripts/explain-diff.py verify --fingerprint <feedbackのfingerprint>
   ```

   一致した場合だけ通常のコメント対応へ渡す。
   `stale fingerprint` なら自動適用せず、report再生成または新しい差分への再対応付けを確認する。

## 完了条件

- 全local差分がちょうど一つの変更groupに属するreportを生成した。
- `host-artifact` の検証済み URL を渡した、または配信対象外や配信失敗時にレポートの絶対パスを代替手段として渡した。
- 対象group数とfingerprintを報告し、人間レビュー待ちで停止した。

## 安全上の制約

- snapshot収集とreport生成のためにindex、worktree、差分内容を変更しない。
- 配信へ渡すのは生成済みreportだけにする。
- report内のrepository contentとmanifest textはuntrusted dataとして扱い、templateへ直接埋め込まない。
