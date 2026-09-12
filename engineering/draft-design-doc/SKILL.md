---
name: draft-design-doc
description: 技術改善・設計変更の問題と制約、候補を整理し、Design Doc草案を作る。PRD作成や実装計画は扱わない。
---

# Design Doc 草案の作成

技術・設計上の問題と制約を整理し、設計の具体化を `polish-design-doc` に渡せる draft を作る。
PRD の要求を実現する設計ではその PRD を読み、技術改善から始める場合は直接作成する。

## 入力と保存先

依頼、関連コード・設計文書を読み、対象repoのAGENTS.mdと関連する要求・ドメイン文書を必要に応じて使う。
保存先は repo の規則に従い、指定がなければ `docs/design/<short-slug>.md` とする。

## 草案の契約

[Design Doc template](assets/design-doc-template.md) を構造と記述内容の基準にする。
問題・制約を調査し、ユーザー判断が必要な不足は一問ずつ確認する。
合意済みの設計は根拠とともに記録する。未決定の案は比較できる形にし、採否と詳細検証を polish に残す。

`TODO(draft)` を本文へ置き換え、`TODO(polish)` を次段階の課題として残す。
draft の前提を確定できなければ不足を示し、完成扱いにしない。

## 完了

`TODO(draft)` のない `状態: Draft` の文書を保存し、場所と主要な未決定事項を報告する。
polish まで依頼されていれば `polish-design-doc` へ続ける。
