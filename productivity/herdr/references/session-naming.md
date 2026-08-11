# Herdr session の初回命名

最初の実質的なタスクで、現在 agent が generic 名のままなら agent と tab を一度だけ命名する。
tab label は主タスクを表し、pane label は変更しない。

## 現在地と命名状態

`herdr pane current` の一つの response から `pane_id` と `tab_id` を取得する。
続いて `herdr tab get <tab-id>`、`herdr agent get <pane-id>`、`herdr agent list` を読む。

`agent get` response に `name` があれば命名済みなので、tab と agent のどちらも変更せず終了する。
`name` がない場合だけ、tab label から次の分岐を選ぶ。

| tab label | tab 操作 | agent 名の入力 |
|---|---|---|
| ASCII の番号だけ | 最初の task label へ rename | 最初の task label |
| 非番号 | 変更しない | 既存 tab label |
| 空 | 変更せず停止 | なし |

非番号の tab label は、人間が付けた名前または前回の部分成功で残った task label として保護する。
同じ tab に複数の generic agent がいる場合も tab label は上書きしない。

## 名前の生成

task label は最初の依頼を人間が識別できる短い表現にし、ASCII の語を含める。
agent 名は canonical label を ASCII 小文字化し、`[a-z0-9]` 以外の連続を `-` に置換して前後の `-` を除く。

- agent 名は `[a-z][a-z0-9_-]{0,31}` を満たす最大32文字とする。
- stem が空または先頭が `[a-z]` でなければ変更せず、命名不能として報告する。
- `agent list` の全 live agent 名と照合し、衝突時は32文字以内で `-2`、`-3` の順に未使用名を探す。
- 未使用名を生成できなければ変更せず、対象 pane ID と衝突を報告する。

## 実行順と再試行

番号だけの tab label は、`herdr tab rename <tab-id> <task-label>` が成功した場合だけ、stable な pane ID を target に `herdr agent rename <pane-id> <agent-name>` を実行する。
非番号の tab label は tab を変更せず、既存 label から生成した agent 名で agent rename だけを実行する。

- tab rename が失敗したら agent rename へ進まない。
- agent rename が失敗したら停止する。agent は generic のままなので再試行できる。
- 再試行では非番号になった tab label を canonical label とし、後続タスクから名前を作り直さない。
- rename 後も agent 操作には同じ pane ID を使う。

現在の generic agent の初回 rename と、番号だけの現在 tab の rename は自律実行してよい。
別 agent、命名済み agent、非番号の tab label、pane label、`--clear` は自動変更の対象にしない。
