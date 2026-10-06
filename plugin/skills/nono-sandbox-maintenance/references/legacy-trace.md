# legacy trace

`nono learn` は0.68.0でdeprecatedなので通常 pathでは使わない。auditやdenial reportで観測できず、legacy traceが必要な場合だけ、ユーザー承認後に限定commandへ使う。

```sh
nono learn --trace --timeout <seconds> -- <command> <args...>
```

macOSで `fs_usage` などのために `sudo` が必要なら、実行前にユーザーへ確認する。
credential読取、公開操作、破壊的操作をdiscovery目的で追加実行しない。
