---
name: prototype
description: Web・mobile/native の見た目、情報設計、操作感、または状態遷移・データ構造・API の感触を、複数案を操作して比較できる throwaway prototype で検証するときに使う。採用済み案の production 実装、静止画 mock だけの作成、通常の技術調査や設計文書作成だけの依頼では使わない。
---

# Prototype

設計上の問いを、既存 project の中で動く比較可能な artifact に変える。
prototype は判断材料であり、production code の先行実装ではない。

## Branch Router

最初に検証対象を一つ選び、対応する reference を読む。

| Branch | 選択条件 | Reference |
| --- | --- | --- |
| Web UI | Web の見た目、情報設計、操作感を比較する | [references/ui-web.md](references/ui-web.md) |
| Native UI | mobile/native の見た目、情報設計、操作感を比較する | [references/ui-native.md](references/ui-native.md) |
| Logic | 状態遷移、データ構造、API の使い心地を操作して確かめる | [references/logic.md](references/logic.md) |

UI と logic の両方が未確定なら、ユーザーの判断を最も左右する問いから一つずつ検証する。
採用案の production 実装へ目的が変わった場合は、この skill を終了し、通常の実装 workflow へ渡す。

## Workflow

1. **問いを固定する。**
   - 一回の prototype で答える比較可能な問いを一文にする。
   - 観察する差と、判断する人が比較時に見る観点を明らかにする。
   - 問いが複数残る場合は、一つを選ぶか prototype を分ける。

2. **既存 project の足場を確認する。**
   - repository instructions、runtime、task runner、routing、component system、近い画面や domain model を調べる。
   - 新しい基盤を持ち込まず、既存の起動経路と表現を再利用する。
   - production 環境への mutation、外部への副作用、不要な永続化が起きない境界を定める。

3. **構造の異なる案を作る。**
   - 原則3案、問いに必要な場合だけ最大5案にする。
   - 色や文言だけでなく、問いに関係する情報配置、操作順、状態表現、model 境界を変える。
   - UI は既存画面へ埋め込み、実際の layout とデータ密度の中で比べる。
   - branch reference に従い、一つの起動方法から案を切り替えられるようにする。

4. **比較に必要な範囲だけ検証する。**
   - project に合う typecheck、build、analyze、起動確認を行う。
   - 各案へ到達でき、同じ前提データで差を操作・観察できることを確認する。
   - prototype の判断に寄与しない production 品質の抽象化、網羅的 test、error handling は追加しない。

5. **判断を引き渡す。**
   - 実行方法、各案の意図、既知の省略、検証結果を伝える。
   - 採用案と理由、未解決事項を issue や設計文書など project の記録先へ残す。
   - prototype code をそのまま production へ昇格させず、採用した知見を通常の実装へ移す。

## Authority Boundary

- commit、push、参照用 branch の公開、issue 更新は、ユーザーの明示依頼または既に与えられた権限がある場合だけ行う。
- live data、production API、端末外の利用者へ影響する操作が必要なら、実行前に安全な代替を探し、なければユーザーへ確認する。
- prototype switcher、debug menu、fixture は production build や通常導線へ露出させない。

## Completion

次をすべて満たしたら完了する。

- 固定した問いに対して、構造的に異なる案を一つの実行方法で操作・比較できる。
- project 相応の静的検証と起動確認の結果を報告できる。
- 実行方法、各案の差、省略した品質、採用判断の記録先をユーザーへ示せる。
- production へ残す知見と捨てる prototype code が区別されている。
