# SRT artifact 分類

この reference は、`SKILL.md` の Step 2 または Step 3 で artifact 分類が必要になったときだけ読む。

## 背景

Anthropic Sandbox Runtime (`srt`) は filesystem write を allowlist で制御する。
Linux では bubblewrap を使う。
bubblewrap は危険な path を保護するため、host に存在しない path に bind mount point を作ることがある。
cleanup が実行されない、または完了できない場合、空 file や空 directory が repository worktree に残って見えることがある。

代表的な protected names:

- `.bashrc`
- `.bash_profile`
- `.gitconfig`
- `.gitmodules`
- `.zshrc`
- `.zprofile`
- `.profile`
- `.ripgreprc`
- `.mcp.json`
- `.git/hooks`
- `.git/config`
- `.vscode/`
- `.idea/`
- `.claude/commands/`
- `.claude/agents/`

## 分類ガイド

次のいずれかに当てはまる candidate は、sandbox artifact の可能性が高い。

- `ls -la` が `crw-rw-rw-` のような device entry を示す。特に owner が `nobody nogroup` の場合。
- protected name の想定外の 0 byte dotfile である。
- protected directory name と一致する想定外の空 directory である。
- `mount` に repository 配下の bind mount、tmpfs、bubblewrap、sandbox 関連 entry が出る。
- sandboxed command の失敗または中断後に path が現れた。

`secrets` のような secret 風 path は protected name とは限らない。
device entry、mount entry、または sandboxed command 直後に現れた事実があれば likely artifact とし、空 directory であるだけなら inconclusive として扱う。
「srt 実行後に気づいた」だけでは直後に新規出現した evidence とみなさない。ユーザーの明言、timestamp、直前の `git status` などで裏取りできない場合は inconclusive として扱う。

次の場合は inconclusive として扱う。

- 内容を持つ通常 file である。
- sandbox failure より前から存在していた。
- repository documentation や tracked files から参照されている。
- 別 process が正当に作成した可能性がある。

## 安全な対応

likely または inconclusive な candidate には、次を守る。

1. 自動削除しない。
2. `.gitignore` に自動追加しない。
3. broad pattern で staging しない。
4. 意図した変更だけを明示 path で staging する。
5. cleanup の前に candidate list をユーザーに見せる。

## 明示確認なしでは危険な command

```bash
git add .
git clean -fd
git clean -fdx
rm -rf <candidate-path>
git rm <candidate-path>
```
