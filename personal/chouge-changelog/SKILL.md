---
name: chouge-changelog
description: CHANGES.md が存在する repository で、git diff、commit、PR、release 内容から CHANGES.md 向けの変更履歴を書く。CHANGES.md がない場合は自動起動しない。
---

# Chouge Changelog

`CHANGES.md` が存在する repository で、git diff、commit、PR、release 内容から、読み手が「何が変わったか」「影響は何か」を把握できる変更履歴を書く。

## 原則

- commit message の焼き直しにしない。diff が利用できる場合は、必ず実際の差分を読む。
- 作業内容ではなく、利用者・運用者・開発者にとって観測できる変化を書く。
- 意図、影響範囲、互換性、移行手順を diff から断定できない場合は捏造しない。
- 変更分類は必要なものだけ出す。空の見出しを作らない。
- 自動起動は `CHANGES.md` が存在する場合だけに限定する。
- `CHANGES.md` がある場合は、その形式・粒度・言語に合わせる。
- `CHANGES.md` がない場合は自動で作成しない。ユーザーが明示的に作成を依頼した場合だけ、最小形式を提案する。

## 変更範囲の確認

ユーザー指定がなければ、まず対象範囲を確定する。

- staged changes: `git diff --staged`
- working tree: `git diff`
- branch diff: `git diff <base>...HEAD`
- commit range: `git diff <from>..<to>`
- PR: `gh pr diff` または base branch との差分

対象範囲が曖昧で、複数の解釈で結果が変わる場合は確認する。

## CHANGES.md の扱い

1. repository root の `CHANGES.md` を確認する。

   ```bash
   root=$(git rev-parse --show-toplevel 2>/dev/null)
   test -n "$root" && test -f "$root/CHANGES.md"
   ```

2. `CHANGES.md` が見つからない場合は、自動で changelog を書かない。ユーザーが明示的に新規作成を依頼している場合だけ、作成案を提示する。

3. `CHANGES.md` が見つかった場合は、次を読み取って合わせる。
   - 見出し形式
   - `Unreleased` の有無
   - version / date の書き方
   - 分類名
   - 箇条書きの粒度
   - 言語

4. ユーザーが `CHANGES.md` の新規作成を明示した場合は、次の最小形式を提案する。

   ```md
   # Changes

   ## Unreleased

   ### Added
   - ...
   ```

## デフォルト形式

`CHANGES.md` に既存分類がない場合は、該当する分類だけを使う。

```md
## Unreleased

### Added
- 新しく追加された機能、設定、コマンド、API。

### Changed
- 既存機能の挙動変更、仕様変更、UI 変更、デフォルト値変更。

### Deprecated
- 将来削除予定になった機能、設定、API。

### Removed
- 削除された機能、設定、API、互換性。

### Fixed
- バグ修正、不具合解消、回帰修正。

### Security
- 脆弱性修正、認証・権限・secret 取り扱いの改善。

### Internal
- 利用者に直接見えない実装変更、リファクタリング、CI、開発基盤。
```

`Internal` は、changelog の読者に意味がある場合だけ使う。利用者向け release note では省略してよい。

## 書き方

- 1項目は原則1つの変更にする。
- 主語は、変更された機能・コマンド・設定・API に置く。
- 「〜を修正」「〜を追加」だけで終えず、可能なら何が改善されたかを書く。
- 破壊的変更は通常の項目に混ぜず、`Removed` または `Migration Notes` で明示する。
- migration が必要な場合は、変更内容と利用者が取るべき対応を分けて書く。
- issue / PR 番号を書く既存慣習がある場合だけ、末尾に `(#123)` のように付ける。

良い例:

```md
### Changed
- `apm.yml` の user-scope install 設定を APM 0.14.2 の `target: claude,agent-skills` 形式に更新した。
```

避ける例:

```md
### Changed
- apm 設定を修正した。
```

## 言語

- ユーザーが言語を指定した場合は従う。
- 既存の `CHANGES.md` の言語に合わせる。
- `CHANGES.md` を新規作成する明示依頼があり、言語指定もない場合は日本語で書く。

## 出力先別の調整

### CHANGES.md に追記する場合

- 既存の `Unreleased` があればそこへ追記する。
- `Unreleased` がなければ、既存形式を壊さない場所に追加案を提示する。
- 同じ内容の項目が既にある場合は重複追記しない。

### GitHub Release Note の場合

- 利用者向けの変更を先に書く。
- 内部変更、依存更新、CI 変更は、重要なものだけ短くまとめる。
- 破壊的変更と migration note を目立つ位置に置く。

### PR 用 changelog entry の場合

- PR 本文全体ではなく、changelog に入る粒度の項目だけを書く。
- レビュー手順やテスト結果は混ぜない。

## Safety Checks

次の場合は、changelog を断定せず確認事項として分離する。

- diff から利用者影響を判断できない。
- 変更範囲が未確定である。
- version / release date が未定である。
- breaking change かどうか判断できない。
- `CHANGES.md` が存在しない。

## Closeout

完了報告には次を含める。

- 対象にした差分範囲。
- 更新または提案したファイル。
- 追加した分類。
- 未確認事項があれば、その一覧。
