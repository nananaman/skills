---
name: tdd
description: 機能追加、バグ修正、仕様変更、リファクタリングをテスト駆動で進めるとき、Red→Green→Refactor を public contract 単位で実行する。よほどの微修正でないコード変更では原則使う。文言・表示データ・translation table のみ、コメントのみ、テスト実行だけ、CI 失敗調査だけでは使わない。
---

# TDD

実装前に外から観測できる契約を定義し、失敗するテストを確認してから最小実装へ進む。
この skill は TDD の進め方を制御する。個々のテストの命名、Arrange / Act / Assert、1 テスト 1 関心、mock / fake、文言固定を避ける判断は `test-writing-style` の観点を適用する。

## When to use

- 機能追加、バグ修正、仕様変更を行うとき。
- リファクタリング前に既存の振る舞いを守れているか確認するとき。
- ユーザーが TDD、テスト駆動、test-first、red-green-refactor、失敗するテストからの実装を求めたとき。
- よほどの微修正ではないコード変更を行うとき。

使わない場面:

- typo、コメント、README など runtime behavior が変わらない軽微変更。
- 文言、表示データ、translation table のみの変更。
- テストコマンドを実行するだけのとき。
- CI 失敗原因を調査するだけのとき。

TDD を適用しない場合は、実装前または報告時に理由を 1 文で明示する。

例:

- 文言・translation table のみで、type / state / route / formatting rule は変わらないため新規テストは追加しない。
- 既存 integration test が同じ public contract を既に守っているため、内部 helper の unit test は追加しない。
- コメント修正のみで runtime behavior が変わらないため、テストは実行確認に留める。

## Principles

- テストは implementation detail ではなく、public interface から観測できる behavior / contract を検証する。
- 全テストを先に書かない。1 behavior ごとに `RED → GREEN → Refactor` を縦切りで進める。
- behavior change を伴う変更では、RED を観測するまで GREEN 実装へ進まない。
- behavior change を伴わないリファクタリングでは、RED cycle ではなく safety-net 観測として扱う。
- GREEN までは現在のテストを通す最小実装に留める。
- Refactor は GREEN 後だけ行い、各 refactor step 後に relevant tests を実行する。
- 重要経路、複雑な分岐、過去バグ、境界条件を優先し、既に守られている契約の重複テストを増やさない。

## Workflow

1. **既存の入口とテストを読む**
   - 変更対象の public interface、user-visible behavior、API contract を確認する。
   - 同じ層・同じ機能周辺の既存テストを読み、test command と helper を把握する。
   - 既存テストが今回守りたい contract を既に十分に守っているか確認する。

2. **テスト対象にする契約を 1 つ選ぶ**
   - 実装手順ではなく、外から観測できる条件と期待結果として書く。
   - 追加テストが必要な契約だけを選ぶ。文言や表示データを写経するだけのテストは書かない。
   - 複数 behavior がある場合も、まず 1 つだけ選ぶ。

3. **RED: failing test を書く**
   - behavior change を伴う変更では、public interface / user-visible behavior / API contract 経由で失敗させる。
   - バグ修正では、現在の不具合を再現する regression test を書く。
   - behavior change を伴わないリファクタリングは Refactoring 節に従い、既存 behavior の safety net を先に確認する。
   - テストを書くときは `test-writing-style` の観点を適用する。

4. **RED を実行して確認する**
   - behavior change を伴う変更では、focused test を実行し、期待した理由で失敗することを確認する。
   - RED を観測できない場合、GREEN 実装へ進んではならない。
   - 観測できない場合は、何を実行したか、期待した failure、実際の blocking reason、環境を整える解決案、より小さい focused test に切り替えられるかを報告して止める。

5. **GREEN: 最小実装を書く**
   - 現在の failing test を通すために必要な最小変更だけを行う。
   - 将来の behavior を先取りしない。
   - 内部構造に合わせてテストを緩めたり、失敗理由を変えたりしない。

6. **GREEN を確認する**
   - focused test が pass することを確認する。
   - 必要に応じて近接する relevant tests も実行する。

7. **Refactor**
   - GREEN を保ったまま、重複、命名、責務分離、module boundary を整える。
   - refactor 中に behavior change が必要になったら、通常の RED cycle に戻る。

8. **次の behavior へ進む**
   - まだ必要な contract が残っている場合だけ、次の 1 behavior で RED から繰り返す。

## Choosing test level

public contract を守れる最小のテストレベルを選ぶ。

1. 既存 integration / contract test が同じ契約を十分に守っているなら、新規テストを追加しない。
2. 複数 module の協調、永続化、service / handler / usecase の主要 behavior は、public interface 経由の focused integration-style test を優先する。
3. 純粋関数、変換、正規化、validation rule、境界値、期間計算、複雑な分岐は unit test を使う。
4. E2E は主要フロー、routing、browser / native / external system との結合リスクが高い場合だけ使う。

server / backend では、service / handler / usecase / repository などの public interface を通した integration-style test を優先する。既存の integration-style test が同じ contract を守っている場合、内部関数や private helper の unit test を重複追加しない。

## Text and display-data changes

文言、表示データ、translation table のみの変更では、新規テストを原則追加しない。
テストすべきなのは表示文字列そのものではなく、文字列を選ぶ元になる contract である。

- validation なら error message ではなく error type / field / code。
- empty state なら表示文言ではなく empty state の種別。
- CTA ならラベルではなく route / href / action / tracking contract。
- legal / disclaimer なら本文ではなく required key / URL / structured requirement。
- i18n なら翻訳文ではなく key の存在、fallback、formatting rule。

文字列を直接検証するのは、その文字列自体が外部契約・法務要件・公開 API 互換性であり、別の構造化 contract として表現できない場合に限る。

## Refactoring

リファクタリングでは、先に既存テストが対象の public behavior を守っているか確認する。

- 十分なら、新規テストは追加せず、既存テストを safety net として使う。
- 不足しているなら、実装変更前に characterization test を追加して既存 behavior を固定する。
- private helper や内部構造を固定する characterization test は避ける。
- characterization test は既存挙動を固定するため、最初から GREEN になることがある。この場合は RED ではなく safety-net 観測を完了条件にする。
- 追加・既存の safety net を実行できない場合は、何を実行したか、blocking reason、環境を整える解決案を報告して止める。
- リファクタ中に behavior change が必要になった場合は、通常の RED cycle に戻る。

## Mocking boundaries

- mock / fake は外部 API、時刻、乱数、filesystem、必要な DB 境界など system boundary に限定する。
- 自分たちが制御する内部 collaborator は、できるだけ実物を使う。
- 呼び出し順、private method、内部関数の分割など、実装詳細だけを検証しない。

## Per-cycle checklist

- 今回守る contract を 1 文で説明できるか。
- 新規テストは本当に必要か。既存テストと重複していないか。
- public interface / user-visible behavior / API contract 経由で検証しているか。
- 文言や表示データそのものを固定していないか。
- behavior change では focused test の RED を期待した理由で観測したか。
- リファクタリングでは既存 behavior の safety net を GREEN として観測したか。
- GREEN 実装は現在のテストを通す最小量か。
- GREEN 前に refactor していないか。
- test-writing-style の観点を満たしているか。
