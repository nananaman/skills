# Herdr helper agent の名前生成

agent が直前に作成した補助 pane で helper agent を起動するとき、pane label から一意な agent 名を生成する。
現在 tab、既存 pane、既存 agent の label や name は変更しない。

## 名前の生成

pane label を ASCII 小文字化し、`[a-z0-9]` 以外の連続を `-` に置換して前後の `-` を除く。
空または先頭が `[a-z]` でない stem には `helper` または `helper-` を補い、人間向けの pane label と agent 名の制約を分離する。

- agent 名は `[a-z][a-z0-9_-]{0,31}` を満たす最大32文字とする。
- `agent list` の全 live agent 名と照合し、衝突時は32文字以内で `-2`、`-3` の順に未使用名を探す。
- 未使用名を生成できなければ agent を起動せず、対象 pane ID と衝突を報告する。
