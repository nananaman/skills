# 日次の実行手順

初回は評価予算`max_runs=0`で、許可された記録の取得・振り返り・未評価候補まで進める。比較評価・正本変更・Git/GitHub/APM操作は起動しない。予定の作成は呼出側が担当する。

## 設定と期間を固定する

[入力・状態契約](contract.md)に従い、端末、許可reader・入力repo、改善先と管理主体、scope、非公開のsource/target・state・出力先、予算・操作範囲を確かめる。改善先だけを入力repoにしない。個人と各組織は分離し、今回の保守rootと評価rootを除外する。

初回は直近24時間の開始〜cutoffを固定する。以後はcheckpoint・未完了turn・未取得期間・反映claimを照合する。取得下限より古いcheckpointなら、許可された再開期間を確認し、自動で巻き戻さない。source/root/unit/revisionとbindingを保持し、別readerや新stateで同じ事例を増やさない。

## Codex記録を取得する

[Codex reader](../scripts/codex_reader.py)は公式CLI proxyで既存daemonへ接続する。元のCODEX_HOME、実行端末、CLI/server版を契約と照合する。必要なsandbox承認は各操作の正式な手続きで得る。拒否後はその対象を停止し、別host・DB・生ログ・別readerへ切り替えない。

```sh
python3 <skill-root>/scripts/codex_reader.py index \
  --source <private/source.json> --state <private/state.json> \
  --since <authorized-start> --cutoff <fixed-cutoff> \
  --codex-home <original-CODEX_HOME> --output <private/index.json>
python3 <skill-root>/scripts/codex_reader.py turns \
  --selection <private/index.json> --codex-home <original-CODEX_HOME> \
  --output <private/turns.json>
python3 <skill-root>/scripts/codex_reader.py read --read-completed \
  --selection <private/turns.json> --state <private/state.json> \
  --codex-home <original-CODEX_HOME> --output <private/export.json>
```

各段階は前段の成功時だけ進む。indexは一覧メタデータ、turnsは本文なしの時刻・終了状態を選び、readは許可された終了turnの本文・tool証拠を最小化する。`read --read-completed`は本文取得を許可された実行だけで使う。取得範囲、完了時刻、ページ上限、既知未完了の条件は契約に従う。

readerの標準出力と`index.result.json / turns.result.json / export.result.json`を確認する。成功状態は`index-selection-verified / turn-selection-verified / export-verified`。blocked・scope-held・coverage不足なら次へ進まず、未取得として報告する。readerはcheckpointを更新しない。

## 収集・振り返り・記録

```sh
python3 <skill-root>/scripts/maintenance.py collect \
  --input <private/export.json> --target <private/target.json> \
  --repo <skill-checkout> --state <private/state.json> --output <private/batches> \
  --since <authorized-start> --cutoff <fixed-cutoff> --new-evidence-only
```

返されたbatchのcaseと予算を確認し、選ばれた事例だけを[振り返り手順](retrospective.md)で分析する。必要な候補をskill-workbenchへ渡し、評価予算0なら未評価のままGit外へ残す。変更不要は正常な判断だが、取得不足・保留・評価不能をno-changeにしない。

`--new-evidence-only`による保留caseは新規turn・証拠revisionで再開する。評価環境・fixture・許可が新しく整った場合の通常collectによる再開は、その変化と操作範囲を確認する。毎日の起動でflagを外して同じ入力を再評価しない。未記録の中断とapplyingの照合は契約に従う。

契約の判断状態に合わせたdecision JSONを作り、次で記録する。

```sh
python3 <skill-root>/scripts/maintenance.py record \
  --batch <private/batch.json> --result <private/decision.json> \
  --state <private/state.json> --repo <skill-checkout>
```

次の状態遷移には保存export・同cutoffでcollectし直して最新batchを使う。外部反映は本体の許可とclaim条件を満たす場合だけ行う。

## 結果と再開

期間、取得範囲・coverage_notes・除外・持越し、処理件数・対象repo、採否と理由、未評価候補、未取得・保留・次回再開条件を短く返す。`awaiting-evidence / held_cases / held_case_ids`は新証拠待ち、`no-new-input`は対象入力なしとして報告する。私的な会話・秘密・ID・証拠を公開repoやPRへ転記しない。

取得・変換・coverage失敗ではcheckpointを進めず、許可範囲内の同じ対象から再開する。反映途中は実際の外部状態を照合してから記録し、再反映を先に実行しない。
