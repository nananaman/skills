## コミットメッセージ

project に明文化された commit 規約がある場合はそれに従う。
ない場合は Conventional Commits に沿う。

- subject は日本語の説明形にする。
- Conventional Commits の scope は任意。
- breaking change は Conventional Commits の `!` または `BREAKING CHANGE:` で示す。

## コミットの粒度

1 commit は 1 つの目的にまとめる。
unrelated changes を同じ commit に混ぜない。
format-only change や generated file の大規模差分は、可能なら実質変更と分ける。

## コミット本文

subject だけで意図や影響が伝わらない場合は body を書く。
body では「何を変えたか」よりも「なぜそうしたか」を優先する。
