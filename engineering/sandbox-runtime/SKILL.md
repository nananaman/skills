---
name: sandbox-runtime
description: Anthropic Sandbox Runtime (srt) の残留 dotfile、bubblewrap の mount 成果物、読み取り専用ファイルシステム、GitHub workflow の権限不足、gh auth refresh による hosts.yml への書き込み失敗を診断する。sandbox 実行後に想定外の未追跡ファイルが残る、または srt 内で認証ファイルへの書き込みが失敗するときに使う。Docker や container 一般の調査、通常の Git の後処理、sandbox と無関係な GitHub 認証設定には使わない。
---

# Sandbox Runtime のトラブルシューティング

Anthropic Sandbox Runtime (`srt`) の挙動とリポジトリの実変更を切り分け、安全な次の操作を決める。

## 手順

### 1. 症状を分類する
1. ユーザーが直近のコマンド出力を提示している場合は、それを観測事実として使う。不足している確認だけを実行する。
   ```bash
   git status --short
   git rev-parse --show-toplevel
   ```
2. `git status --short` または提示された観測事実に、想定外の dotfile や機密情報らしいパスが出る場合は、手順2に進む。
3. コマンドが `read-only file system`、`Operation not permitted`、書き込み拒否で失敗する場合は、手順3に進む。
4. `.github/workflows/*` の変更の push が token の `workflow` 権限不足で拒否される場合は、手順4に進む。
5. どれにも該当しない場合は、この skill を使わない。

### 2. 残留成果物の候補を確認する
1. 依頼された作業と無関係なパスだけを候補にする。例：`.bashrc`、`.gitconfig`、`.profile`、`.zshrc`、`.claude/agents`、`.idea`、`secrets`。
2. `<candidate-paths>` を手順1で選んだ候補パスに置き換えて、次を実行する。
   ```bash
   ls -la <candidate-paths>
   mount | grep "$(git rev-parse --show-toplevel)" || true
   ```
3. `references/srt-artifacts.md` を読んで出力を分類する。
4. 候補一覧をユーザーに見せて明示確認を取るまで、削除、`.gitignore` への追加、`git clean` を実行しない。
5. ステージは意図した変更だけを明示したパスで行う。
   ```bash
   git add <intended-path>
   ```

### 3. sandbox の書き込み拒否を扱う
1. srt write allowlist 外への書き込みは、反証が出るまで sandbox policy による失敗として扱う。
2. 失敗したパスがユーザーの home 配下の場合、sandbox 設定や home 内のファイルを自動編集しない。
3. 失敗したコマンドが `gh auth refresh` で、エラーに `hosts.yml` が含まれる場合は、手順4に進む。
4. それ以外の書き込み拒否では、`references/srt-artifacts.md` を読み、拒否されたパス、試みた操作、書き込み可能領域の外に見えるかを報告する。

### 4. GitHub workflow の権限不足を扱う
1. 次を実行する。
   ```bash
   gh auth status -h github.com
   git config --show-origin --list | grep -E 'insteadOf|remote\.origin|credential' || true
   ```
2. `Token scopes` に `workflow` がなければ、ユーザーに sandbox の外で次を実行してもらう。
   ```bash
   gh auth refresh -h github.com -s workflow
   ```
3. srt 内で実行済みの `gh auth refresh` が `hosts.yml: read-only file system` で失敗していた場合、srt 内で再試行しない。
4. ユーザーが認証情報を更新した後、`gh auth status -h github.com` を再実行し、`Token scopes` に `workflow` が含まれることを確認する。
5. Git config が SSH remote を HTTPS に rewrite している場合、SSH push で回避できると決めつけない。

### 5. 結果を報告する
1. `assets/report-template.md` の構成で報告する。
2. 実行したコマンドと観測した事実だけを書く。
3. 破壊的操作や認証情報の変更は「ユーザー確認が必要」と明記する。

## 安全ルール

- 残留成果物の候補が作業ツリーに残っている間は、`git add .` を実行しない。
- 成果物の候補に対する `git clean`、`git reset --hard`、`rm`、`.gitignore` の変更は、ユーザー確認なしで実行しない。
- device code、token、機密情報の内容、認証ファイルの内容を記録しない。
- `hosts.yml: read-only file system` 失敗後に、srt 内で `gh auth refresh` を再実行しない。
- commit、push、APM pin 更新、install は、この skill の診断結果として自動実行しない。ユーザーが現在の依頼で明示している場合だけ、別の Git / APM 手順として扱う。

## エラー時

- `mount` の出力が取れない、リポジトリと無関係な項目が多すぎる、またはリポジトリ配下との対応を判断できない場合は、`ls -la` による分類を続け、mount の状態は不明として報告する。
- `gh auth status` がネットワークや認証情報へのアクセスで失敗した場合は、機密情報を含まないエラーだけを報告し、sandbox 外での認証情報の確認を依頼する。
- 候補ファイルが通常のユーザー作成ファイルに見える場合は、成果物としての扱いを止め、後処理やステージの判断前にユーザーへ確認する。

## 完了条件

- 成果物の候補、書き込み拒否、workflow の権限、SSH への切り替えのうち、該当する症状を分類した。
- 実行した確認コマンドと観測事実を報告した。
- 安全な次の操作と、ユーザー確認が必要な操作を分けて提示した。
