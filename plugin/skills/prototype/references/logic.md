# ロジックのプロトタイプ

状態遷移、データ構造、API の使い心地や成立性を、小さな実行可能 harness から観察する。

## 構造

1. API capability など単一の成立性 spike は、再現可能な入力と観察可能な結果を持ち、一つの command で動く直接的な script または harness にしてよい。
2. 状態や連続操作を観察する場合は、検証する model と、入力を受け付け表示する shell を分離する。
3. stateful / interactive な model は一回の操作を受け、関連する state、event、derived value、error を観察可能な形で返す。
4. harness または shell は project の既存 runtime から一つの command で起動する。task runner は project に存在し、問いの再現に必要な場合だけ使う。
5. 比較する場合は variant ごとに public operation を揃え、同じ入力または操作列を適用できるようにする。

## 操作と観察

- stateful / interactive な prototype は、reset 可能な初期 state と、問いに必要な seed data を memory 上に置く。
- 状態遷移を観察する場合は、一操作ごとに before / input / after と、判断に必要な派生値を表示する。
- 単一の成立性 spike は、入力条件と結果を同じ command で再現できるようにする。
- invalid transition、境界値、操作順依存が問いに関係する場合は、再現可能な操作列を用意する。
- 外部 API が論点でも network call 自体が論点でなければ、request / response の形だけを local adapter で再現する。

## 境界

- database、queue、remote API、filesystem への永続化を既定にしない。
- production 用 migration、retry、observability、汎用 framework を prototype のために追加しない。
- shell の都合を model の interface に混ぜない。

## 確認

- project 標準の typecheck / build と起動 command を実行する。
- 単一 spike は問いへの答えを再現し、比較する場合は各 variant に同じ代表操作列を適用して差が出る state と結果を記録する。
- 起動 command、再現可能な入力または操作例、観察結果、意図的に省いた production concern を報告する。
- stateful / interactive な prototype では reset 方法も報告する。
