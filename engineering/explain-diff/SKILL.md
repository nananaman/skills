---
name: explain-diff
description: 実装意図を保持するセッションから、staged・unstaged・untrackedを含むlocal差分を意図別・リスク順に解説し、人間が確認とコメントを行う自己完結HTMLを生成するときに明示的に使う。コード品質レビュー、finding生成、修正、branch / commit / PR差分には使わない。
disable-model-invocation: true
---

# Explain Diff

現在のlocal差分を、ファイル順ではなく変更意図ごとのグループとして人間へ説明する。
意味のあるmodule依存や処理flowを説明できる場合は図で俯瞰してから、groupごとの解説とhunkへ掘り下げられる形にする。
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

3. snapshotの `hunks` を読み、同じ変更意図に従属するhunkをまとめる。
   [`references/manifest-contract.md`](./references/manifest-contract.md) に従って、snapshotと同じdirectoryへ `manifest.json` を作る。
   renameと追従import修正のような機械的変更も、同じ目的なら一groupにする。
   依存関係、状態遷移、時系列を説明することがレビューを助ける場合はMermaidの `diagrams` を作る。
   flowchartのnodeは役割が分かる名称と説明を持たせ、`node_links` でgroup・hunk・用語へ結び付ける。
   importやfile一覧を並べただけになる場合は省略する。
   repository固有の名称、新しい概念、略語が解説や図に登場する場合は `glossary` で、この変更における意味を定義する。

4. reportを生成して開く。

   ```sh
   python3 <skill-directory>/scripts/explain-diff.py render \
     --snapshot <snapshot.json> \
     --manifest <manifest.json> \
     --output <snapshot-directory>/report.html
   ```

   CLIが全hunkの一意な割当とmanifest contractを検証する。
   validation errorはmanifestを直して再実行する。
   `stale snapshot` はlocal差分が変わった証拠なので、古いmanifestを流用せずStep 2からやり直す。
   browser openerがなければstdoutの絶対pathをユーザーへ渡す。

5. reportの対象、group数、fingerprint、生成pathを伝える。
   ユーザーがhostを依頼した場合だけ、foreground serverを起動する。

   ```sh
   python3 <skill-directory>/scripts/explain-diff.py serve --report <report.html>
   ```

   既定は `127.0.0.1` と空きportで、localhostだけからアクセスできる。
   Tailscale経由を依頼された場合は現在のTailscale IPv4を確認し、`--host <Tailscale IPv4>` でそのinterfaceだけにbindする。
   LAN経由も同様に対象interfaceのIPv4を確認して明示する。
   requested interfaceを特定できない場合は `0.0.0.0` へ広げず、配信せずに理由を伝える。
   portを固定する場合は `--port <number>` を使う。
   reportはlocal差分全文を含むため、LAN公開はユーザーの明示依頼なしに行わない。
   serverはreport一つだけを配信し、`Ctrl-C`までforegroundで稼働する。

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
- reportをbrowserで開いた、または開ける絶対pathを渡した。
- hostを依頼された場合は指定されたnetwork境界でのアクセス方法を渡し、稼働状態を報告した。
- 対象group数とfingerprintを報告し、人間レビュー待ちで停止した。

## Safety

- snapshot収集とreport生成のためにindex、worktree、差分内容を変更しない。
- `要改善` は説明と差分の対応に関する警告であり、コードfindingや自動修正依頼として扱わない。
- report内のrepository contentとmanifest textはuntrusted dataとして扱い、templateへ直接埋め込まない。
