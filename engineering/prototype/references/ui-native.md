# Mobile / Native UI Prototype

mobile/native の見た目、情報設計、操作感を debug build 上で比較する。

## 組み込み方

1. 対象画面の navigation、state management、design system、fixture の慣習を確認する。
2. 既存画面の実際の scaffold や navigation 内へ variant を埋め込む。
3. platform と project に合う debug 限定 selector を一つ選ぶ。
   - overlay、bottom bar、debug menu、開発用 setting などを使う。
   - URL や deep link は project が既に採用している場合だけ使う。
4. 同じ fixture と端末条件で全案へ移動できることを確認する。

## Flutter を macOS で比較する場合

- project が macOS target をサポートするか確認し、既存の Flutter command と device 選択を使う。
- mobile 固有 API は adapter または fixture で隔離し、UI の問いに不要な platform 実装を増やさない。
- macOS window の初期サイズを揃え、mobile 相当の layout 条件が必要なら明示的な constraint を使う。
- `flutter analyze` と対象 macOS build または起動確認を行い、代替した platform behavior を報告する。

## 境界

- selector、fixture、fake service は debug build からだけ到達可能にする。
- permission、purchase、notification、remote write は実行せず、観察に必要な response を局所的に再現する。
- animation や gesture が問いに関係する場合は、静止状態だけで完了としない。

## 確認

- project 標準の analyze / build と、利用する target での起動確認を行う。
- selector の場所、検証した device / window 条件、代替した native behavior を報告する。
