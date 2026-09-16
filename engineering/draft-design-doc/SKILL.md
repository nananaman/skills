---
name: draft-design-doc
description: 技術改善・設計変更、または PRD 後に必要な大きい変更について Design Doc draft を作る。問題・制約と既存の設計判断を整理し、未決定の案を比較できる形にする。PRD 作成、Design Doc polish、issue 作成、実装、レビューだけの依頼では使わない。
---

# Design Doc 草案の作成

技術・設計上の問題と制約を整理し、設計の具体化を `polish-design-doc` に渡せる draft を作る。
PRD の要求を実現する設計ではその PRD を読み、技術改善から始める場合は直接作成する。

## 入力と保存先

依頼、関連コード・設計文書を読み、repo-local の `docs/agents/engineering-flow.md`・`domain.md` があれば使う。
保存先は repo の規則に従い、指定がなければ `docs/design/<short-slug>.md` とする。

## 草案の契約

[Design Doc template](assets/design-doc-template.md) を構造と記述内容の基準にする。
文書の読者、用途、読者に求める判断・行動を [`chouge-writing`](../../writing/chouge-writing/SKILL.md) の文書の契約として整理する。テンプレートの構造は変更せず、既存の目的や概要など適切な節へ必要な情報を記載し、placeholder は実値に置き換える。
問題・制約を調査し、ユーザー判断が必要な不足は一問ずつ確認する。
合意済みの設計は根拠とともに記録する。未決定の案は比較できる形にし、採否と詳細検証を polish に残す。

`TODO(draft)` を本文へ置き換え、`TODO(polish)` を次段階の課題として残す。
draft の前提を確定できなければ不足を示し、完成扱いにしない。

## 完了

- 文書の読者、用途、読者に求める判断・行動が、テンプレートの構造を変えずに文書へ反映されている。
- `TODO(draft)` のない `状態: Draft` の文書を保存し、場所と主要な未決定事項を報告する。
polish まで依頼されていれば `polish-design-doc` へ続ける。
