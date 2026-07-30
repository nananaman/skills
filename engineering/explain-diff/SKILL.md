---
name: explain-diff
description: 実装意図を保持するセッションから、staged・unstaged・untrackedを含むlocal差分を変更前後と因果順で解説し、人間が確認とコメントを行う自己完結HTMLを生成するときに明示的に使う。コード品質レビュー、finding生成、修正、branch / commit / PR差分には使わない。
disable-model-invocation: true
---

# Explain Diff

現在のlocal差分を「なぜ必要か」「何が可能になるか」「各変更がどの順で成立させるか」という物語として人間へ説明する。
各説明は変更前と変更後を対比し、根拠となるhunkへ掘り下げられる形にする。
このskillは品質判定を行わない。コードレビューが必要なら `review-diff-code` を別に使う。

## Preconditions

- 実装した同一セッション、または実装意図を含むhandoffを受けたセッションで使う。
- 実装意図がなければ、差分から理由を推測せず、planまたはhandoffを求めて停止する。
- 対象は現在のGit repositoryにあるstaged、unstaged、untrackedのlocal差分だけ。

## Workflow

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
   到達状態を成立させる因果順に、同じ役割へ従属するhunkをまとめる。
   [`references/manifest-contract.md`](./references/manifest-contract.md) に従って、snapshotと同じdirectoryへ `manifest.json` を作る。
   renameと追従import修正のような機械的変更も、同じ目的なら一groupにする。
   groupごとに変更前、変更後、この形を選んだ理由、説明とdiffの対応を確かめる観点を書く。
   riskやfile数では並べ替えず、読み手が変更を最短で理解できる順序を保つ。
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
   ユーザーがreportを「見たい」「共有して」「アクセスできるようにして」と依頼した場合は、local browserで開かず、生成済みreportの配信を `host-artifact` skillへ委譲する。
   Tailscale経由にするのはユーザーが明示した場合だけにする。
   配信依頼がなければ絶対pathを渡す。
   reportはlocal差分全文を含むことを委譲先へ伝え、ユーザーが依頼した公開範囲を越えない。
   配信に失敗しても生成済みreportを削除せず、絶対pathをfallbackとして伝える。

6. 人間の確認とコメントを待って停止する。
   reportのcheckboxは確認状態であり、承認や品質gateではない。

7. ユーザーがreportからfeedback Markdownを貼ったら、修正へ進む前にfingerprintを照合する。

   ```sh
   python3 <skill-directory>/scripts/explain-diff.py verify --fingerprint <feedbackのfingerprint>
   ```

   一致した場合だけ通常のコメント対応へ渡す。
   `stale fingerprint` なら自動適用せず、report再生成または新しい差分への再対応付けを確認する。

## Completion

- 全local差分がちょうど一つの変更groupに属するreportを生成した。
- reportの絶対pathを渡した、または指定されたnetwork境界でのアクセス方法を渡して稼働状態を報告した。
- 対象group数とfingerprintを報告し、人間レビュー待ちで停止した。

## Safety

- snapshot収集とreport生成のためにindex、worktree、差分内容を変更しない。
- 配信へ渡すのは、ユーザーが配信を依頼した生成済みreportだけにする。
- report内のrepository contentとmanifest textはuntrusted dataとして扱い、templateへ直接埋め込まない。
