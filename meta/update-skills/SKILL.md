---
name: update-skills
description: APMのskill依存を最新化し、manifest・正本・展開先を同期する。本文の改善や通常のpackage更新には使わない。
disable-model-invocation: true
---

# APM skill 依存関係の更新

`dependencies.apm` の参照先を最新化し、指定がなければ install と反映確認まで行う。
manifest・scope・許可・hash mismatch の共通規則は [apm-usage](../apm-usage/SKILL.md) に従う。
skill 本文の編集・品質改善は対象外。

## 更新手順

1. ユーザー指定と manifest を照合して対象を決める。グローバルでは `~/.apm/apm.yml` の実体を確認する。scope が会話から確定しない場合は確認する。
2. `git status --short` で既存変更を把握し、他者の変更を保護する。今回の変更と判明している差分について所有者を再確認しない。
3. 依存関係を GitHub 参照とローカル path に分け、同じ repository の取得をまとめる。
4. 以下の規則で更新し、変更前後の commit と更新できない理由を記録する。
5. manifest の差分と参照先・scope・target を確認し、変更リスクに応じて `skill-workbench` の差分レビューを使う。配布に影響する未解決の指摘があれば install を保留する。保留対象を含む manifest は一括で展開しない。対象を除外して安全に install できると確認できなければ、その manifest 全体の install を保留する。
6. install 不要の指定がなければグローバルは `apm install -g`、project は repository 直下で `apm install` を実行し、展開先への反映を確認する。取得・検証に失敗した対象は更新済みとして扱わず、前項の install 保留規則に従う。

### GitHub 参照

- `git ls-remote https://github.com/<owner>/<repo>.git HEAD` などでデフォルトブランチの最新 full SHA を取得する。別 ref の指定があればそれを使う。
- 同じ repository の複数パスは、別 ref の指定がない限り同じ commit に揃える。pin がない項目も full SHA に固定する。
- manifest は SHA のみを更新し、path、owner、repo、target、既存の形式を変えない。変更がない項目はそのままにする。

### ローカル path

参照先 repository ごとに fetch し、branch、working tree、upstream との差を確認する。
デフォルトブランチにいて clean かつ fast-forward できる場合だけ、`git merge --ff-only <upstream>` で最新化する。
それ以外は参照先を変更せず状態を報告し、その対象について判断を待つ。無関係な対象の調査・manifest 更新は続けるが、install は上記の保留規則に従う。
manifest の path は変更しない。

## 完了と報告

対象 manifest と実体パス、更新した依存関係の変更前後、更新できなかった項目と理由、install と反映確認の結果を簡潔に報告する。
更新数が多い場合は表を使う。変更・install・反映確認のどこまで完了したかを区別する。
commit / push は通常の完了条件に含めない。
