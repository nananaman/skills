---
name: draft-prd
description: 新機能・仕様変更の一言アイデア、メモ、会話ログ、既存 issue から PRD draft を作る。問題・対象ユーザー・要求と既存の判断を整理し、未決定のプロダクト案を比較できる形にする。技術設計、Design Doc 作成、issue 作成、PRD polish、実装、レビューだけの依頼では使わない。
---

# PRD 草案の作成

新機能・仕様変更の問題、対象ユーザー、要求を整理し、具体化を `polish-prd` に渡せる draft を作る。
技術設計は Design Doc、実装手順は実装計画で扱う。

## 入力と保存先

依頼と関連文書を読み、repo-local の `docs/agents/engineering-flow.md`・`domain.md` があれば使う。
保存先は repo の規則に従い、指定がなければ `docs/prd/<short-slug>.md` とする。

## 草案の契約

[PRD template](assets/prd-template.md) を構造と記述内容の基準にする。
問題・要求を調査し、ユーザー判断が必要な不足は一問ずつ確認する。
合意済みの案は根拠とともに記録する。未決定の案は比較できる形にし、採否の判断を polish に残す。

`TODO(draft)` を本文へ置き換え、`TODO(polish)` を次段階の課題として残す。
draft の前提を確定できなければ不足を示し、完成扱いにしない。

## 完了

`TODO(draft)` のない `状態: Draft` の文書を保存し、場所と主要な未決定事項を報告する。
polish まで依頼されていれば `polish-prd` へ続ける。
