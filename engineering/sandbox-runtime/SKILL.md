---
name: sandbox-runtime
description: Anthropic Sandbox Runtime (srt) の ghost dotfiles、bubblewrap mount artifact、read-only filesystem、GitHub workflow scope 不足、gh auth refresh の hosts.yml 書き込み失敗を診断する。sandbox 実行後に想定外の untracked files が残る、または srt 内で認証ファイルへの書き込みが失敗するときに使う。Docker/container 一般の調査、通常の Git cleanup、sandbox と無関係な GitHub 認証設定には使わない。
---

# Sandbox Runtime Troubleshooting

Anthropic Sandbox Runtime (`srt`) の挙動と repository の実変更を切り分け、安全な次アクションを決める。

## 手順

### Step 1: 症状を分類する
1. ユーザーが直近の command output を提示している場合は、それを観測事実として使う。不足している確認だけを実行する。
   ```bash
   git status --short
   git rev-parse --show-toplevel
   ```
2. `git status --short` または提示された観測事実に、想定外の dotfile や secret 風 path が出る場合は、Step 2 に進む。
3. command が `read-only file system`、`Operation not permitted`、write denial で失敗する場合は、Step 3 に進む。
4. `.github/workflows/*` の変更 push が token の `workflow` scope 不足で拒否される場合は、Step 4 に進む。
5. どれにも該当しない場合は、この skill を使わない。

### Step 2: ghost artifact 候補を確認する
1. 依頼された作業と無関係な path だけを候補にする。例: `.bashrc`, `.gitconfig`, `.profile`, `.zshrc`, `.claude/agents`, `.idea`, `secrets`。
2. `<candidate-paths>` を 1 で選んだ候補 path に置き換えて、次を実行する。
   ```bash
   ls -la <candidate-paths>
   mount | grep "$(git rev-parse --show-toplevel)" || true
   ```
3. `references/srt-artifacts.md` を読んで出力を分類する。
4. candidate list をユーザーに見せて明示確認を取るまで、削除、`.gitignore` 追加、`git clean` を実行しない。
5. staging は意図した変更だけを明示 path で行う。
   ```bash
   git add <intended-path>
   ```

### Step 3: sandbox write denial を扱う
1. srt write allowlist 外への書き込みは、反証が出るまで sandbox policy による失敗として扱う。
2. failure path が user home 配下の場合、sandbox 設定や home file を自動編集しない。
3. 失敗した command が `gh auth refresh` で、error に `hosts.yml` が含まれる場合は、Step 4 に進む。
4. それ以外の write denial では、`references/srt-artifacts.md` を読み、denied path、試みた操作、writable area 外に見えるかを報告する。

### Step 4: GitHub workflow scope 失敗を扱う
1. 次を実行する。
   ```bash
   gh auth status -h github.com
   git config --show-origin --list | grep -E 'insteadOf|remote\.origin|credential' || true
   ```
2. `Token scopes` に `workflow` がなければ、ユーザーに sandbox 外で次を実行してもらう。
   ```bash
   gh auth refresh -h github.com -s workflow
   ```
3. srt 内で実行済みの `gh auth refresh` が `hosts.yml: read-only file system` で失敗していた場合、srt 内で再試行しない。
4. ユーザーが credential を refresh した後、`gh auth status -h github.com` を再実行し、`Token scopes` に `workflow` が含まれることを確認する。
5. Git config が SSH remote を HTTPS に rewrite している場合、SSH push で回避できると決めつけない。

### Step 5: 結果を報告する
1. `assets/report-template.md` の構成で報告する。
2. 実行した command と観測した事実だけを書く。
3. 破壊的操作や credential 変更は「ユーザー確認が必要」と明記する。

## 安全ルール

- ghost artifact 候補が worktree に残っている間は、`git add .` を実行しない。
- artifact 候補に対する `git clean`、`git reset --hard`、`rm`、`.gitignore` 変更は、ユーザー確認なしで実行しない。
- device code、token、secret 内容、credential file 内容を記録しない。
- `hosts.yml: read-only file system` 失敗後に、srt 内で `gh auth refresh` を再実行しない。
- commit、push、APM pin 更新、install は、この skill の診断結果として自動実行しない。ユーザーが現在の依頼で明示している場合だけ、別の Git / APM 手順として扱う。

## エラー時

- `mount` output が取れない、repository と無関係な entry が多すぎる、または repository 配下との対応を判断できない場合は、`ls -la` による分類を続け、mount state は不明として報告する。
- `gh auth status` が network や credential access で失敗した場合は、secret を含まない error だけを報告し、sandbox 外での credential 確認を依頼する。
- candidate file が通常の user-created file に見える場合は、artifact 扱いを止め、cleanup や staging 判断の前にユーザーへ確認する。

## 完了条件

- artifact 候補、write denial、workflow scope、SSH fallback のうち該当する症状を分類した。
- 実行した確認 command と観測事実を報告した。
- 安全な次 action と、ユーザー確認が必要な操作を分けて提示した。
