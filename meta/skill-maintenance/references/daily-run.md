# 日次の実行手順

本人・所属組織が管理する許可済みrepoで、取得・振り返り・skill-workbenchによる評価・改修・検証・draft PR作成まで進める。予定の作成・更新は呼出側が担当する。merge・APM更新・installは別の明示依頼が必要。新規契約・課金設定・認証・アクセス権を追加しない。

収集からPR提出までの実行手順はこの文書を正本とし、スケジューラpromptへ複製しない。単独依頼・別端末でも同じ順序で実行し、その環境で許可されたsource・reader・接続・操作範囲を確認する。別端末の登録や承認を引き継いだとは扱わない。

呼出側はtarget/source/state・非公開出力先・対象checkout・readerと元CODEX_HOME・予算・確認済み操作範囲を渡す。既定期間と予算は以下を使い、取得・評価・PR作成の業務手順を呼出し文へ追加する必要はない。

```text
skill-maintenanceを実行する。
設定: <target/source/state・非公開出力先・対象checkout・reader/元CODEX_HOME>
許可操作: 編集・commit・push・draft PR作成/更新
```

この操作範囲は対象repoについて実際に委任された場合だけ指定する。設定値・この呼出し例を外部操作の許可の代わりにしない。

## 設定と期間を固定する

[入力・状態契約](contract.md)に従い、端末、許可reader・入力repo、改善先と管理主体、scope、非公開のsource/target・state・出力先、予算・操作範囲を確かめる。改善先だけを入力repoにしない。個人と各組織は分離し、今回の保守rootは下記で登録し、評価rootはsourceの`exclude_roots`に登録して除外する。

依頼された入力元を列挙し、source別の許可readerと取得結果を記録する。CodexとWorkの履歴を同じ一覧だと仮定しない。未対応sourceは明示して接続・実装を自動追加せず、native取得は共通export、Work自己申告は後述の別intakeで分析する。全体coverageと分析できる入力範囲を分ける。

Codex nativeの初回は直近24時間の開始〜cutoffを固定する。Workは許可済みtaskの未回収完了turn差分を対象とし、元時刻不明でも選定できる。以後はcheckpoint・未完了turn・未取得期間・反映claimを照合する。取得下限より古いcheckpointなら、許可された再開期間を確認し、自動で巻き戻さない。source/root/unit/revisionとbindingを保持し、別readerや新stateで同じ事例を増やさない。

一晩の既定予算は`budget: {max_cases: 1, max_runs: 12}`。1件の診断に絞り、現行版と最小変更1候補を、開発・候補選択・最終確認それぞれ2ケース（失敗条件と成功・制約を守る反例）で比較する計12実行に使う。単発の観測差として報告し、反復なしで統計的な改善を主張しない。両側・失敗・中断も数え、未評価の反復や追加候補を際限なく実行しない。既存の契約・利用枠だけを使い、実行不可・予算切れ・退行・差が不確実なら保留する。決定的な誤字・リンク修正はworkbenchの軽量経路でよい。複数targetでは全体で1件・12実行を配分し、個人・組織のケースや結果を混ぜない。

`max_runs`はworkbenchの`run`に相当する候補・ケース・反復ごとの実行を1回と数える。開始した失敗・timeout・中断・再試行も消費し、CLIが記録保存に成功したことを評価合格へ読み替えない。採点はこのrun数に含まれないため、同じケースの親子成果を匿名で独立採点する呼出しは最大6回、独立した差分レビューは最大1回に制限する。必要なら決定的な検査を使う。これらをモデルで行う場合も既存の利用枠だけを使い、不足・拒否・未採点ならPRへの反映を保留する。

候補実行は編集会話を継承せず、採点担当へ期待する勝者や診断履歴を渡さない。trainの2ケースで失敗と安定成功・制約を対比し、別の元タスク群のvalidationとtestを各2ケース用意する。候補を1案に絞り、validationで選んだ版だけをtestで最終確認する。testを修正に使ったらtrainへ移し、残予算で新しい最終確認を揃えられなければ未検証として保存する。

日次target.jsonの`budget`へこの値を設定してcollectのbatchに渡す。予算はtarget identityに含まれないため、値の変更だけで新stateを作らず、既存checkpointと重複防止を維持する。起動側の「候補抽出のみ・評価0」という指定も同時に整合させるが、スケジュールや自己収集契約の変更をこの予算から許可しない。

## 日次を新規開始する

現行7項目のsource、許可済みsource repo・target、確認済み保守・評価rootの除外を照合する。各段階のbyte/time予算を起動引数に指定し、Codex初回の開始とcutoff（直近24時間）を固定して非公開に記録する。Work初回は可視範囲の未回収完了turnを対象とし、既存受信済みreportとそのhost確認済みreply turnを再回収しない。

初回stateは未作成または判断・checkpointのない空の台帳から始める。`register-run`は現在rootだけを登録し、初回の成功exportをcollectしてからcheckpointを作る。次回以後はcheckpoint・未完了turn・未取得window・反映claimから再開する。外部反映前には現在の正本と既存PRを照合し、同目的の変更を重ねない。

## 保守runを登録する

履歴取得前に、この実行自身のroot IDを同じ非公開台帳へ登録する。現在のrunは除外し、次回以降に終了したrunの失敗事実だけを取得できる。取得失敗でも登録だけが残り、checkpointは進まない。

```sh
python3 <skill-root>/scripts/maintenance.py register-run \
  --target <private/target.json> --repo <skill-checkout> \
  --state <private/state.json> --source-id <registered-source-id> \
  --root-id <current-maintenance-root-id>
```

登録済み保守runも既存のsource repo・scope・端末の条件を満たす必要がある。source allowlistへ自動追加しない。初回prompt、assistantの提案・採点・成功報告、評価root・子runは取り込まない。後続の記録されたユーザー入力は指摘候補であり、roleだけで人間の指摘や許可を証明しない。定期promptを棄却し、実際のユーザーの不満・訂正と確認できる内容だけを診断する。失敗や指摘がない日は候補を作らない。

## Codex記録を取得する

[Codex reader](../scripts/codex_reader.py)は公式CLI proxyで既存daemonへ接続する。元のCODEX_HOME、実行端末、CLI/server版を契約と照合する。必要なsandbox承認は各操作の正式な手続きで得る。拒否後はその対象を停止し、別host・DB・生ログ・別readerへ切り替えない。

```sh
python3 <skill-root>/scripts/codex_reader.py index \
  --source <private/source.json> --state <private/state.json> \
  --since <authorized-start> --cutoff <fixed-cutoff> \
  --max-bytes 67108864 --max-seconds 300 \
  --codex-home <original-CODEX_HOME> --output <private/index.json>
python3 <skill-root>/scripts/codex_reader.py turns \
  --selection <private/index.json> --codex-home <original-CODEX_HOME> \
  --max-bytes 67108864 --max-seconds 300 \
  --output <private/turns.json>
python3 <skill-root>/scripts/codex_reader.py read --read-completed \
  --selection <private/turns.json> --state <private/state.json> \
  --max-bytes 67108864 --max-seconds 300 \
  --codex-home <original-CODEX_HOME> --output <private/export.json>
```

過去24時間の対象を件数で打ち切らず、期間の古い境界またはcursor終端まで必要なページを取得する。APIの1ページのlimitは分割単位であり、取得総数の上限ではない。各段階の既定予算はWebSocketの受信payload 64 MiB・経過300秒、3段階を各1回なら最大192 MiB・15分（owned proxyの終了処理を除く）。予算にはinitialize・通知・捨てるreasoning等のpayloadも含め、フレーム本文を読む前に残量と照合する。改善評価の12実行とは別の予算である。

`incomplete`・exit 2・`output_written:false`なら次段階とcollectへ進まない。同名の古いoutputを成功結果と誤認しない。結果JSONの`resume`に失敗段階と固定window、非公開の`*.progress.json`を残し、当該sourceのcheckpointは変えず、そのsourceの取得を停止する。検証済みの別sourceは進められる。次回は同じwindow・入力・state・出力先で失敗段階を再実行する。保存済みの最小化ページを再利用し、最初の未取得cursorから通信を再開するので、同じ有限予算でも前進できる。未取得cursorを成功したcheckpointにしない。

windowごとに別の非公開出力ディレクトリを使い、未取得windowの再試行ではそのディレクトリを維持する。新windowは成功exportのcollect後に始める。progressはscope・window・入力・state・元CODEX_HOME・protocolに結び付け、整合性digestとlockを検査する。reasoning・preview・title・生引数を保存せず、indexは正規化した出所・時刻、turnsは本文なしの時刻・状態、readは最小化済みの本文・証拠だけを保持する。再開時も本文取得前にthreadの出所とidle状態を読み直し、現在rootを除外する。再開indexの各一覧の先頭ページを毎回取得して関連行を照合するが、daemonの履歴一覧のtransaction snapshotを保証するものではない。

binding・digest・cursor・一覧順序や先頭の不一致は`blocked`としてprogressとcheckpointを保持する。自動削除・先頭へのfallback・別readerへの切替はしない。同じ許可window・scopeでの明示的な再取得が必要なら、原因を確認してprogressを非公開に退避し、新しい出力先を使う。アクセス拒否の回避には使わない。保存失敗やexport容量超過で前進できない場合も必要量・原因を報告し、次回の有限予算または許可期間内の時間分割を決める。未取得期間やscopeを黙って捨てず、成功した時間区間だけを古い順にcollectする。

各段階は前段の成功時だけ進む。indexは一覧メタデータ、turnsは本文なしの時刻・終了状態を選び、readは許可された終了turnの本文・tool証拠を最小化する。`read --read-completed`は本文取得を許可された実行だけで使う。取得範囲、完了時刻、ページ上限、既知未完了の条件は契約に従う。

readerの標準出力と`index.result.json / turns.result.json / export.result.json`を確認する。成功状態は`index-selection-verified / turn-selection-verified / export-verified`。blocked・scope-held・incomplete・coverage不足なら次へ進まず、未取得として報告する。readerはcheckpointを更新しない。

## Work の自己申告を取り込む

許可済みtaskをhostの正規list/readで列挙し、latestTurn.id/statusを最小metadataへ正規化する。attachedAtを完了時刻へ転用しない。選定CLIが未回収完了turn IDを先に持越すため、retry中の新turnも返信で隠れない。完了した振り返り返信のturn IDもintakeで既回収にする。

```sh
python3 <skill-root>/scripts/maintenance.py select-retrospectives \
  --input <private/host-metadata.json> --target <private/target.json> \
  --repo <skill-checkout> --state <private/state.json> --max-reports 2 \
  --exclude-root <known-host-maintenance-or-derived-task-id>
```

選定結果のrequested_tasksだけに依頼し、v2 envelopeへ元completed_turn_idと実際のreceipt_turn_idを渡す。新完了turnでは同task/report IDのrevisionを増やす。進行中taskには依頼しない。未受信retryは保存した元turn IDを維持する。

閉じた実務taskの許可されたhost送信・読取は[portable retrospective intake](work-retrospective.md)に従う。最大2 task requests・5分/64 MiBのhost予算、intake 8 MiBを守り、未対応・失敗・保留・時刻不明を残す。日次skillを受けたhostがtask選定・send/read・Macへのenvelope委譲を行い、Macはintake結果を返す。具体的な境界と再開は同referenceの「日次起動から Mac への最小 handoff」に従う。host能力が日次contextに露出しない場合は自動要求が成立したとせず、未対応を報告する。hostが未対応でも、検証済みCodexの分析は進められる。Work自己申告batchはnative取得manifestのcollected行へ入れず、受信状態と可視差分の受信状態を別に報告する。source履歴coverageはunknownのまま、時刻不明を新基準のblockerにしない。旧windowは過去v1入力の出所記録として維持し、差分へ時刻を補わない。

```sh
python3 <skill-root>/scripts/maintenance.py intake-retrospectives \
  --input <private/work-retrospectives.json> --target <private/target.json> \
  --repo <skill-checkout> --state <private/state.json> --output <private/work-batches> \
  --max-reports 2 --new-evidence-only
```

## 収集・振り返り・記録

```sh
python3 <skill-root>/scripts/maintenance.py collect \
  --input <private/export.json> --target <private/target.json> \
  --repo <skill-checkout> --state <private/state.json> --output <private/batches> \
  --since <authorized-start> --cutoff <fixed-cutoff> --new-evidence-only
```

`--expected-source-id`には依頼時に列挙した全sourceを指定する（以下はCodexとWorkの例）。sourceごとの取得終了後、成功したbatchと未対応・失敗の分類codeを[契約](contract.md)の非公開manifestへ記録し、集計する。reader失敗時の古いbatchを成功行へ入れない。

```sh
python3 <skill-root>/scripts/maintenance.py report \
  --acquisitions <private/acquisitions.json> --target <private/target.json> \
  --repo <skill-checkout> --state <private/state.json> \
  --since <authorized-start> --cutoff <fixed-cutoff> \
  --expected-source-id <registered-codex-source-id> --expected-source-id work \
  --output <private/source-report.json>
```

未対応・失敗があっても成功sourceのbatchを振り返れる。ただし未取得sourceの証拠を必要とする事例は保留し、部分取得を全体成功にしない。共通exportの不完全coverageをcollectへ通すことは引き続き禁止する。reportはcheckpointを更新せず、取得成功したsourceのcollectだけがそのsourceを進める。

返されたbatchのcaseと予算を確認し、選ばれた事例だけを[振り返り手順](retrospective.md)で分析する。必要な候補をskill-workbenchへ渡し、固定した条件で親子比較・独立採点・holdoutを行う。単発のtool障害から万能な規則を作らず、再現・反例と照合して最小変更を選ぶ。変更不要は正常な判断だが、取得不足・保留・評価不能をno-changeにしない。

`--new-evidence-only`による保留caseは新規turn・証拠revisionで再開する。評価環境・fixture・許可が新しく整った場合の通常collectによる再開は、その変化と操作範囲を確認する。毎日の起動でflagを外して同じ入力を再評価しない。未記録の中断とapplyingの照合は契約に従う。

契約の判断状態に合わせたdecision JSONを作り、次で記録する。

```sh
python3 <skill-root>/scripts/maintenance.py record \
  --batch <private/batch.json> --result <private/decision.json> \
  --state <private/state.json> --repo <skill-checkout>
```

次の状態遷移には保存export・同cutoffでcollectし直し、自己申告は保存envelopeでintake-retrospectivesを再実行して最新batchを使う。外部反映は本体の許可とclaim条件を満たす場合だけ行う。

## 評価からdraft PRへ進む

対象repoの規約に従う独立したbranch/worktreeで改修・必要検証・差分レビューを行う。本人・所属組織の管理を実体で確認し、対象repoの編集・commit・push・draft PRが委任されている範囲を使う。各修正の再承認へ戻さず、権限拡張や重大な判断は差分を示して保留する。自身の収集・評価・権限・統合ルールは独立レビューと明示採用まで現行運用へ適用しない。

公開前に差分・commit本文・PR本文・添付物を確認し、会話本文・秘密・私的なID・パス・組織情報を含めない。検証は公開可能な合成fixtureで示し、私的な根拠は同scopeのGit外に残す。公開可能な差分にできなければpush・PRを保留する。

`evaluated`を記録後、対象の正しいremote・base・管理主体を確認し、既存のopen/closed PR、branch・commit、適用済み差分を同目的で照合する。同じ変更のPRがあれば安全にそのPRを更新するか到達点を照合し、新規PRを作らない。不明・権限不足・無関係な既存差分との競合は停止する。新規の場合は`applying`に今回委任された`edit / commit / push / pr`を記録し、pushとdraft PRの成功を実際のSHA・URL・draft状態で確認して`applied`を記録する。ここでのappliedはPR提出の到達点で、merge済みではない。統合後のcloseout・同期は別途依頼された場合だけ実行する。

## 結果と再開

期間、取得範囲・coverage_notes・除外・持越し、処理件数・対象repo、採否と理由、未評価候補、未取得・保留・次回再開条件を短く返す。`awaiting-evidence / held_cases / held_case_ids`は新証拠待ち、`no-new-input`はその成功sourceの対象入力なしとして報告する。source別の`acquired / empty / unsupported / failed`と全体coverageを併記し、未対応・失敗を対象0件へ変換しない。私的な会話・秘密・ID・証拠を公開repoやPRへ転記しない。

定期実行では初回結果、PR作成/更新、取得・実行失敗、権限不足や重要な採用判断など対応が必要な問題を通知する。初回は起動時に該当sourceのcheckpointがない場合とし、以後の変更なし・変化のない既知保留は通知せず、状態と再開に必要な結果を非公開に保持する。単独依頼の結果報告や明示された通知指定には従う。

取得・変換・coverage失敗では当該sourceのcheckpointを進めず、許可範囲内の同じ対象から再開する。反映途中は実際の外部状態を照合してから記録し、再反映を先に実行しない。
