# Engineering Flow

このリポジトリでは、実装前の不確実性を減らすために次の engineering flow を使う。

## 基本フロー

新機能・仕様変更:

```text
draft-prd
  -> polish-prd
  -> draft-design-doc? / polish-design-doc?（大きい変更・後戻りしにくい変更では必須）
  -> draft-issue
  -> polish-issue
  -> implementation
  -> review
```

技術改善・設計変更:

```text
draft-design-doc? / polish-design-doc?
  -> draft-issue
  -> polish-issue
  -> implementation
  -> review
```

小バグ・小リファクタ:

```text
draft-issue
  -> polish-issue
  -> implementation
  -> review
```

軽微な文書・設定変更では、理由が明らかな場合に限り issue flow を省略してよい。

## PRD の責務

PRD は、新機能・仕様変更の要求判断文書である。
作る価値・範囲・成功条件を人間が判断できる状態にする。

PRD で扱うもの:

- 概要とゴール
- やらないこと
- 対象ユーザー / 利用者
- なぜ作るか
- 作るもの
  - 機能概要
  - 主要な振る舞い
  - 受け入れ条件
- 成功条件

PRD は実装計画にしない。
要求に関する TODO は、PRD を polished とする前に解消する。

## Design Doc の責務

Design Doc は、技術・設計上の問題を解くための設計判断文書である。

入口は二つある。

1. 技術・設計上の問題から直接始める場合
   - CI 改善、build 改善、architecture 改善、module 分割、migration strategy など
2. PRD の要求を実現するために必要になる場合
   - API / DB / 状態設計 / 移行 / セキュリティ / 信頼性などの設計判断が必要な変更

Design Doc は、新機能・仕様変更の「何を作るか」「なぜ作るか」「成功条件」を決める文書ではない。
要求の価値・範囲・成功条件を決める必要がある場合は、先に PRD を作る。

Design Doc は次の場合に必須である。

- 複数 issue に分割される
- API / DB / 状態設計 / 互換性 / 移行に影響する
- migration / rollout planning が必要
- 失敗したときの手戻りが大きい、または設計リスクが高い
- 用語、domain model、状態、不変条件、business rule の整理が必要

Design Doc が必要な場合は、issue 作成前に polished にする。
issue polish 中に Design Doc の矛盾を見つけた場合は、issue を block し、先に Design Doc を更新する。

## Polished issue gate

実装は polished issue から開始する。
Polished issue は implementation design contract であり、別 agent がその issue だけを読んで実装に入れる状態である。

Polished issue には次を含める。

- 目的と背景
- 現状
- 要求 / 仕様
- やらないこと
- 設計方針
- 変更境界
- 必要な PRD / Design Doc への参照と要約
- 実装上の注意
- テスト方針
- 完了条件
- 実装に必要な未解決事項がないこと

## Review gate

実装後の review では次を確認する。

- diff の品質と regression risk
- polished issue との整合性
- `やらないこと` に反する scope creep がないこと
- 参照された PRD / Design Doc との整合性
- テスト方針が満たされていること
