# Logic Prototype

状態遷移、データ構造、API の使い心地を、小さな操作用 shell から観察する。

## 構造

1. 検証する model と、入力を受け付け表示する shell を分離する。
2. model は一回の操作を受け、関連する state、event、derived value、error を観察可能な形で返す。
3. shell は project の既存 runtime と task runner から一つの command で起動する。
4. variant ごとに public operation を揃え、同じ操作列を適用できるようにする。

## 操作と観察

- reset 可能な初期 state と、問いに必要な seed data を memory 上に置く。
- 一操作ごとに before / input / after と、判断に必要な派生値を表示する。
- invalid transition、境界値、操作順依存が問いに関係する場合は、再現可能な操作列を用意する。
- 外部 API が論点でも network call 自体が論点でなければ、request / response の形だけを local adapter で再現する。

## 境界

- database、queue、remote API、filesystem への永続化を既定にしない。
- production 用 migration、retry、observability、汎用 framework を prototype のために追加しない。
- shell の都合を model の interface に混ぜない。

## 確認

- project 標準の typecheck / build と起動 command を実行する。
- 各 variant に同じ代表操作列を適用し、差が出る state と結果を記録する。
- 起動 command、操作例、reset 方法、意図的に省いた production concern を報告する。
