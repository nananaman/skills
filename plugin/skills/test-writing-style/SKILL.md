---
name: test-writing-style
description: テストの追加・修正・レビューで、命名、Arrange/Act/Assert、fixtureやmockを既存スタイルと公開契約に合わせる。単なるテスト実行には使わない。
---

# テストの記述規範

失敗したときに、どの条件で何を期待したか読めるテストを書く。
追加するテストと検証範囲は、ユーザー要求、プロジェクトの検証方針、実装作業の指針で判断する。このskillは設定ファイルなどの種別だけで新規テストを要求しない。

## 既存スタイルと構造

同じ言語・層・機能のテストを読み、命名、grouping、fixture、helper、assertionを揃える。
Goでは [references/go.md](references/go.md) も参照する。

- テスト名は、条件と期待結果が分かる仕様文にする。
- 各テスト定義の直前に、ケースの意図を短いコメントで書く。説明はプロジェクトに別指定がなければ日本語にする。
- 正常系と異常系は別のテストにし、境界条件も独立して識別できるケースにする。一つの振る舞いをassertionの数だけに分割しない。
- テスト本体は各段階の先頭に `Arrange` / `Act` / `Assert` の区切りコメントを明示する。短いテストでも省略せず、複雑な準備や副作用の理由は対応するコメントに補足する。
- `Assert` 内では、検証観点ごとの意味のまとまりの直前にコメントを書く。各assertion一行ごとの説明は繰り返さない。
- Actは一つの振る舞いを実行する単位にする。区切りコメントのために処理を分割したり、helperを増やしたりしない。
- 入出力で表せる処理はparameterized / table-driven testを検討する。各ケースの意図はケース定義のコメントに置き、AAAと検証観点のコメントは共通のテスト本体に書く。複雑な副作用を無理に共通helperへ押し込まない。
- 後続の検証に必要な前提はfatal assertionで確かめ、独立した値はまとめて確認できるようにする。

### コメントの例

商品小計8,000円以上は送料無料、合計は小計と送料の和、という架空の仕様を例にする。`CalculateOrder` は商品の単価・数量から `Subtotal`・`Shipping`・`Total`（円）を返す。

```go
// 正常系: 送料無料の条件を満たす注文の合計を計算する。
func TestCalculateOrder_FreeShipping(t *testing.T) {
	// Arrange
	// 小計8,000円で8,000円以上の送料無料条件を満たす。
	items := []OrderItem{
		{UnitPrice: 3000, Quantity: 2},
		{UnitPrice: 2000, Quantity: 1},
	}

	// Act
	got := CalculateOrder(items)

	// Assert
	// 単価と数量から商品小計を計算している。
	if got.Subtotal != 8000 {
		t.Errorf("Subtotal = %d, want 8000", got.Subtotal)
	}

	// 送料無料が適用され、合計は小計のみになる。
	if got.Shipping != 0 {
		t.Errorf("Shipping = %d, want 0", got.Shipping)
	}
	if got.Total != 8000 {
		t.Errorf("Total = %d, want 8000", got.Total)
	}
}
```

## 外から見える契約を検証する

公開インターフェースから結果、エラー、状態遷移、副作用を検証する。private method、内部の呼出順、内部委譲だけを固定しない。

- validationはtype / field / code、UI操作はroute / actionなど、そのテストが守る契約を選ぶ。
- 表示文字列や設定値を写しただけのassertionを増やさない。CLI / API / codegenの出力など文字列自体が契約なら、直接の比較は妥当である。
- promptやSKILL.mdの意味・判断を、特定文言や見出しの存在でテストしたことにしない。構造はfrontmatter、schema、リンクなどを検査し、判断はレビューや必要な実行例で確認する。
- 同じ契約を守る既存テストがあるなら、内部関数向けの重複テストを追加しない。

## 外部依存と副作用

単体テストでは、外部API、時刻、乱数などのsystem boundaryをfake / mockで隔離する。内部の協調オブジェクトは、可能なら実物を使う。
結合テストやE2Eでは、検証対象の境界までmock化しない。専用DB、local server、一時filesystemなど、目的に合う制御可能な環境を使う。
実クラウドや共有環境を使う必要がある場合は、依頼された検証範囲と権限、データの隔離・後処理を確認する。

副作用そのものが契約なら、引数や結果、二重実行、呼ばれてはいけない操作を検証する。呼出回数・順序は、その違いが外部の結果を変える場合に限って固定する。
fixtureは必要な状態だけを作り、取得した資源と変更した共有状態の後処理を直ちに登録する。非同期の後処理は、所有する作業の終了まで待つ。状態遷移の失敗時にも、守るべき不変条件を確認する。
port、一時directory、子process、共有状態、非同期の準備・終了を扱うテストでは、[資源と完了の確認](references/resource-lifecycle.md)も参照する。
