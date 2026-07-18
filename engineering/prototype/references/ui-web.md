# Web UI Prototype

Web の見た目、情報設計、操作感を既存画面の文脈で比較する。

## 組み込み方

1. 対象画面と同じ route、layout、component、fixture の使い方を確認する。
2. 既存画面の一部を variant 境界にし、周囲の navigation、幅、データ密度を保つ。
3. project の routing 機構に合う variant selector を用意する。
   - URL path、query、route parameter など、共有と reload ができる方式を優先する。
   - selector を prototype 専用 component に閉じ込める。
4. 同じ fixture と viewport で全案へ到達し、切り替え後も選択案を再現できることを確認する。

## 比較可能性

- 問いに関係する画面構造や操作順を案ごとに変える。
- loading、empty、long content など、判断を変えうる状態だけ fixture に含める。
- 視覚差だけが目的でなければ、色や装飾だけの variant を案数に数えない。

## 境界

- analytics、server mutation、production data への書き込みは stub または memory 上の反応へ置き換える。
- variant selector と prototype fixture が production bundle や通常 route へ残らない構造にする。
- responsive behavior が問いに関係する場合だけ、代表幅で比較する。

## 確認

- project 標準の typecheck / build と対象 route の起動確認を行う。
- 各 variant の共有可能な指定方法と、比較に使う前提データを報告する。
