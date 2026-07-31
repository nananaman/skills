# Artifact Prototype

HTML report、文書、diagram、可視化の構成や表現を、正式成果物を作る前に観察する。

## Authoring

1. 問いに必要な媒体と忠実度を選ぶ。
2. 媒体固有の制作手順は、利用可能な `documents`、`visualize` などの authoring skill や適切な tool に委ねる。
3. production template、完全な内容、公開用 metadata など、判断に不要な仕上げは行わない。
4. prototype であり正式成果物ではないことを、配置、名前、または表示上の注記で識別できるようにする。

## 観察と比較

- 単一実験では、情報構造、可読性、表現能力など固定した問いへの答えを観察できるようにする。
- 複数案では、内容、データ、表示条件を揃え、問いに関係する構造または表現だけを変える。
- diagram や可視化は、同じ関係やデータを異なる encoding で示す場合に、誤読しやすさも観察する。
- 文書や report は、代表的な長さ、欠損、密度など判断を変えうる条件だけを含める。

## 境界

- prototype を正式な文書、report、diagram、dashboard として公開または配布しない。
- production data や非公開情報は使わず、問いに必要な fixture または匿名化した内容で代替する。
- authoring skill の production 品質基準を、prototype の目的を超えて再実装しない。

## 確認

- 問いに必要な renderer または viewer で artifact を開き、表示崩れや観察不能な状態がないことを確認する。
- 実行または閲覧方法、観察条件、意図的に省いた production concern を報告する。
- 判断後は呼び出し元の lifecycle に従って artifact を廃棄し、残す知見だけを正式な記録先へ移す。
