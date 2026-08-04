# SRT 成果物の分類

この参照資料は、`SKILL.md` の手順2または手順3で成果物の分類が必要になったときだけ読む。

## 背景

Anthropic Sandbox Runtime (`srt`) はファイルシステムへの書き込みを許可リストで制御する。
Linux では bubblewrap を使う。
bubblewrap は危険なパスを保護するため、host に存在しないパスへ bind mount の接続点を作ることがある。
後処理が実行されない、または完了できない場合、空ファイルや空ディレクトリがリポジトリの作業ツリーに残って見えることがある。

代表的な保護対象名：

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

次のいずれかに当てはまる候補は、sandbox が作った成果物の可能性が高い。

- `ls -la` が `crw-rw-rw-` のようなデバイス項目を示す。特に所有者が `nobody nogroup` の場合。
- 保護対象名と一致する想定外の 0 byte dotfile である。
- 保護対象のディレクトリ名と一致する想定外の空ディレクトリである。
- `mount` にリポジトリ配下の bind mount、tmpfs、bubblewrap、sandbox 関連の項目が出る。
- sandbox 内で実行したコマンドの失敗または中断後にパスが現れた。

`secrets` のような機密情報らしいパスは保護対象名とは限らない。
デバイス項目、mount 項目、または sandbox 内のコマンド直後に現れた事実があれば`likely`とし、空ディレクトリであるだけなら`inconclusive`として扱う。
「srt 実行後に気づいた」だけでは直後に新規出現した根拠とみなさない。ユーザーの明言、時刻、直前の `git status` などで裏取りできない場合は`inconclusive`として扱う。

次の場合は`inconclusive`として扱う。

- 内容を持つ通常のファイルである。
- sandbox の失敗より前から存在していた。
- リポジトリの文書や追跡済みファイルから参照されている。
- 別のプロセスが正当に作成した可能性がある。

## 安全な対応

`likely`または`inconclusive`の候補には、次を守る。

1. 自動削除しない。
2. `.gitignore` に自動追加しない。
3. 広いパターンでステージしない。
4. 意図した変更だけを明示したパスでステージする。
5. 後処理の前に候補一覧をユーザーに見せる。

## 明示確認なしでは危険なコマンド

```bash
git add .
git clean -fd
git clean -fdx
rm -rf <candidate-path>
git rm <candidate-path>
```
