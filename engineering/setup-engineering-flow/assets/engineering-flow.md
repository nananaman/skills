# Engineering Flow

このリポジトリでは、共有する設計判断と、個別実装でだけ使う plan を分離する。

## 基本フロー

```text
PRD? / Design Doc? / ADR?
  -> task-breakdown
  -> issue tracker
  -> create-plan <issue> -> review-plan
  -> implementation
  -> verification
  -> simplify-code?
  -> review
  -> commit
  -> create-pr?
```

要求判断が必要な新機能・仕様変更では、task 分解前に PRD を polished にする。
複数 task が共有する設計判断や、後から参照すべき判断は、task 分解前に Design Doc または ADR として合意・永続化する。
小バグ、小リファクタ、軽微な文書・設定変更では、上流文書や task 分解を省略して既存 issue またはユーザー説明から `create-plan` へ進んでよい。

## 永続文書の責務

PRD は「なぜ・何を・どこまで」を判断する。
Design Doc / ADR は、複数 task や将来の変更から参照する技術的な意思決定を残す。
実装時だけ必要な調査結果や作業方針を永続文書へ混ぜない。

## Task の責務

issue tracker の task は、人が共有し、担当者が取得できる作業単位である。

task には次を含める。

- 目的
- 対象範囲 / 対象外
- 完了条件
- 依存する task
- 元になった要求・設計への参照
- 必要な場合だけ、担当 component や変更してよい interface 境界

個別実装の詳細、変更ファイルごとの手順、局所的な実装方法は task に固定しない。
合意済みの情報を複数 task へ分ける場合は `task-breakdown` を使い、分解案の確認後に設定済み tracker へ作成する。

## Plan gate

担当者が task を取得した後、`create-plan <issue>` で実装前の共有理解を作る。
`create-plan` は関連文書とコードを調査し、`grilling` で重要な判断を一つずつ解消してから、repo 設定済みの plan directory に一時 plan を作る。
作成後は`review-plan`を自動実行し、検討漏れと不要な複雑性のblockerがなくなるまでplanを修正する。ユーザー判断や上流設計の変更が必要なfindingでは停止する。

plan directory:

```text
plans/
```

この directory は `.gitignore` に追加しない。

plan の標準見出しは次とする。

- 目的
- 現状
- 設計方針
- 完了条件
- スコープ外

別セッションの coding agent が追加の設計判断なしに実装・検証できる状態を plan gate とする。
plan は今回の実装だけで使う untracked file であり、永続的な Design Doc / ADR の代わりにしない。

## Implementation and review gate

実装中は plan を参照し、plan の完了条件に対応する自動テスト、静的検査、必要な実動作確認を行う。
実装と検証が完了した後、最終コードレビューの前に`simplify-code`を適用する必要があるか判断する。
追加の簡素化が費用に見合わなければ何も変更せず、必要な場合だけ今回の作業に属する差分へ、振る舞いを保った修正を適用して再検証する。
簡素化で差分が変わった場合は、その完成差分をレビューする。
実装後は次を確認する。

- diff の品質と regression risk
- issue の scope と完了条件との整合性
- plan の設計方針と完了条件との整合性
- 上流の PRD / Design Doc / ADR との整合性
- scope creep がないこと

review と修正が終わるまで plan file を保持する。

## Plan closeout

plan file 自体は一度も commit しない。
通常は実装・検証・review・修正後に一つの完成 commit を作る。
commit body には plan 原文を次の marker 内へ入れ、plan file を削除してから commit する。

```text
Implementation-Plan:

<plan 原文>

End-Implementation-Plan
```

途中 commit が必要な場合は最初の commit body に plan を入れ、実装完了まで plan file を保持し、最後の commit 前に削除する。
PR を作る場合は commit body から plan 原文を抽出し、PR body の折りたたみへ同じ内容を転記する。
これにより、直接 push では Git 履歴、squash merge では PR 履歴から実装時の plan を参照できる。
