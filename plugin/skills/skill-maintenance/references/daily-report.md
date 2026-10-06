# 日次のユーザー向けレポート

毎回のskill実行で、取得・診断・候補評価が未完でも、その時点の事実からレポートを生成する。通知条件を満たさない変更なしの日も成果物を残す。nativeの`report`は取得manifestの集計であり、このユーザー向けレポートの代わりではない。

## 日付・保存先と責務

callerの非公開設定は[report-config JSON例](../examples/report-config.json)の`version / report_timezone / information_scope / report_destination（kind・親のreference・information_scope）`を持つ。入力要約と保存先の情報scopeをこの設定に一致させる。`kind`は`host-space / local`、親のreferenceはcallerが解決する非公開の不透明な参照とする。日付はskill実行時刻をこのtimezoneへ変換して決め、取得windowのUTC cutoffと区別する。保存先の個人ページID、組織名、絶対pathをskill本文や公開exampleへ固定しない。保存先scopeは対象の情報区分・利用者が許可した配布範囲と照合する。本人限定のSpaceならhostがその閲覧設定を確認する。匿名化だけで別情報scopeへの転記を許可しない。

本文の作成・証拠との照合・秘密の最小化・Markdown生成・handoffはskillの責務。Spaceの正規APIで保存・読戻しできる許可済みhostが、設定の親配下へ`YYYY-MM-DD スキル振り返り`を作成・更新する。スケジューラは呼出時刻とcaller設定だけを渡し、このworkflowやpromptを複製しない。Space能力のないPCは保存済みMarkdownとhandoffを返し、hostの保存を待つ。新接続・credential・アクセス拡張を行わない。

同日ページが既にあれば読んで正しい日付・scope・親を照合し、今回の追補だけを更新する。再送は同じ日付・scope・内容digestを照合して重複ページ・重複追補を避ける。送信要求の成功、ページ保存の成功、正規APIでの読戻し一致を分けてreceiptへ残す。保存できない・拒否・連携不能なら`delivery-held`として理由・再送用成果物を保持し、保存済みと報告しない。

## 本文に含める内容

- 対象期間と日付基準、今回の結論。部分取得・自己申告・未検証は明記する。
- 対象実務ごとの分かる名前と作業内容、入力元、根拠の種類、取得・対象なし・除外・失敗・持越し・未対応の状態と理由。複数実務を一括成功へまとめない。
- 抽出した改善候補と短い根拠。候補なしと未分析を区別し、同じ元taskのrevisionや親子を独立証拠の数にしない。
- 各候補の検証方法、結果、未確認の範囲、採用・変更不要・見送り・保留の理由。テスト成功、実行比較、実運用確認、外部反映を分ける。
- PRリンク。作成されていなければ「なし」と理由、次の対応・残件・再開条件。

作業名は許可されたmetadataと取得済み証拠からユーザーが分かる短い作業内容へ整理する。元の私的タイトルをそのまま転記しない。取得失敗で名前・内容が分からないときは「作業名未取得」とし、安定した表示ラベルと件数で識別し、タイトルや成功を創作しない。表示ラベルと内部task IDの対応は同scopeの非公開記録だけに置く。除外の本文や進行中taskの本文をレポートのために追加取得しない。

秘密、生ログ、原文引用、生reasoning、私的絶対path、内部ID・cursor・運用設定を本文に含めない。必要な根拠は成果と失敗条件に一般化する。公開GitHub PRのURL以外のリンクを本文へ出すときはこのCLIを拡張する前に別の配布契約を確認する。CLIの検出可能な秘密・path・ID拒否は補助であり、privacyや意味の正しさの証明ではない。出力をhostへ渡す前に本文全体を人または実行担当が確認する。

## PCで再現できる生成とhandoff

skill担当は非公開の取得結果・Work batch・採否台帳・検証結果・実際のPR結果を照合し、[匿名JSON例](../examples/daily-report.json)と同じfieldを持つsanitized inputを作る。内部台帳や生exportをそのまま渡さない。`sessions`は全対象の状態、`candidates`は抽出した候補、`checks`は検証とその限界を列挙する。既存の未変更保留も必要ならその理由を示すが、評価を再実行したと扱わない。未知fieldは拒否する。状態は次の語彙を使う。

- session: `acquired / empty / excluded / failed / held / unsupported / self-report`
- candidate: `adopted / no-change / rejected / held`

```sh
python3 <skill-root>/scripts/maintenance.py daily-report \
  --input <private/sanitized-daily-summary.json> --config <private/report-config.json> \
  --repo <skill-checkout> \
  --output <private/report-YYYY-MM-DD-revision.md>
```

入力・caller設定・出力はGit外。入力が8 MiBを超える場合はskill担当が全項目を番号付き入力へ分け、その全入力を保持する。各入力は8 MiB以下でCLIへ渡し、出力が8 MiBを超える場合はCLIが全UTF-8行を順序付きMarkdown partへ分割する。多数のcheckも行境界で保持し、固定件数で省略しない。各出力名の末尾へ`.handoff.json`を付けた非公開manifestに全partの順序・digest・残part数を保存する。複数入力の全manifestと未処理入力をskill担当が一つのhandoffへ束ね、途中のpartだけで全日完了を主張しない。生成が拒否・失敗なら入力・停止理由を保持し、再開時は同じ入力と新しいrevision pathを使う。既存file・symlink・入力との衝突は上書きしない。生成失敗を通知し、事実の記録を消さない。このCLIは正規化済みsummaryとcaller設定だけを読み、scope・timezone一致を検査し、Markdownと保存用handoffを生成する。設定は権限の証明ではなく、skill担当とhostが実際の入力scope・配布許可・保存先を照合する。CLIは履歴・台帳の取得、ネットワーク、Space保存、評価、native checkpoint更新を行わない。exit 0はMarkdown生成の成功だけであり、`delivery_status: host-handoff-pending`を返す。

生成される非公開handoffは`version:1 / report_date / timezone / information_scope / destination（kind・callerの親参照・scope）/ parts（order・path・sha256）/ remaining_parts / delivery_status / reason`を持つ。part pathは同scopeの許可済み非公開fileで、hostへinline本文を渡す場合は順序とdigestを保つ。本文だけをページへ保存し、内部handoff metadataを本文へ転記しない。未完part・保存不能・確認待ちはその状態を明記する。hostは保存先・scope・日付・全part・内容digestを確認し、`saved / verified / delivery-held`の最小receiptを返す。skillはreceiptを同scopeの非公開rootへ保存し、読戻し未確認をverifiedにしない。

日次通知は従来の初回・PR変更・取得/実行失敗・重要な採用判断の条件を維持する。レポートを毎日生成・指定先へ保存することと、通知することは別である。初回以外の変更なし・変化のない既知保留でもレポートは生成する。
