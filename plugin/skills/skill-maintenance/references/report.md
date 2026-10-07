# 日次レポートと保存

callerのreport-config.jsonからtimezone・information_scope・保存先を解決する。日付はそのtimezone基準とし、取得期間と区別する。入力の情報scopeと保存先の許可範囲を照合する。匿名化だけで別scopeへの転記を許可しない。

毎回、Git外の新しい非公開fileへ掲載用report.jsonを作る。これは表示の正本であり、取得stateや一次振り返り台帳を置き換えない。成果・反省点・対応・検証のつながりを要点にし、説明と根拠は生成Markdownにも残す。対象実務ごとに、分かる作業名、入力元、観測/自己申告、取得状態、結果、学び、未確認事項を記す。対象期間、全対象/取得/振り返り/失敗/残件、開始・終了時計と処理全体のwall time、段階別実測時間、改善候補と根拠、検証と限界、採否と理由、PR、残課題を含める。候補なしと未分析、取得失敗と対象なしを区別する。過去の判断と後日の採用・導入は時点を明記する。

秘密、生ログ、原文引用、推論、私的絶対path、内部ID・cursor・運用情報をJSONにも載せない。私的な作業名はユーザーが分かる短い内容へ一般化する。公開PRのURLは使える。JSONと生成本文を証拠と照合し、privacy検査も行ってからhostへ渡す。rendererはエスケープと型・リンクの検査を行うが匿名化はしない。自動検査だけで秘密がないとは証明しない。

## 表示データと生成

[合成例](../examples/report.json)の薄い形式を使う。文字列はplain text、各一覧は配列。必須はversion（1）、date（YYYY-MM-DD）、timezone（IANA名）。period（取得期間のplain text）、summaryと以下の一覧・timingは省略可能で、省略した一覧は空として表示する。日次レポートではperiodに実際の取得期間、checks.detailなどに発見・対象・取得・振り返り・失敗・残件の集計と範囲を記す。未分析や取得失敗を空一覧だけで表さず、checks・remaining・sessionsに状態と理由を記す。

| 項目 | 内容 |
| --- | --- |
| outcomes | title、change、status（draft / adopted / proposed / no_change / failed）、任意のpr_url |
| reflections | title、happened、next、result、evidence、任意のchange。起きたこと→次の対応→変更→検証を同じ項目に保つ |
| checks | title、result、detail |
| remaining | title、detail。保留理由と必要な判断もdetailに書く |
| sessions | title、source、evidence（history / self_report）、status（read / partial / failed / uncollected / in_progress / held / outside_period / excluded）、detail。結果・学び・未知をdetailに書く。heldは進行中・終端不明・変更検出などの理由を保持する |
| timing | 任意のstart・end（timezone付きISO時刻またはnull）、wall_seconds（秒またはnull）、scope（計測範囲と再利用条件）、stages（title・seconds・detailの配列） |

resultはpassed / failed / partial / unverified。未計測を0にせずnullにする。未知のfieldは受付けない。内部handoff情報をこのJSONへ混ぜない。採用状態は各outcomeへ明示し、テスト成功から推定しない。

```sh
python3 <skill-root>/scripts/render_report.py \
  --input <sanitized-report.json> --repo <improvement-checkout> \
  --output <new-private-directory-outside-git>
```

固定[HTML template](../assets/report.html)からreport.htmlとreport.mdを生成する。毎回モデルにHTMLを書かせない。外部fetchや依存追加は不要。pr_urlはcredential・query・fragmentを含まない絶対HTTP(S) URLだけ。出力は新規directory（0700）とfile（0600）で、元JSON・既存出力を上書きしない。I/O失敗はexit 1で、途中出力は照合用に保持し、完成handoffに使わない。再生成は新しいdirectoryへ行う。

HTMLの256 KiB UTF-8上限はPage visualizationの制約。超過時は切り詰めず表示生成を失敗として返し、正本JSONと取得・振り返り結果を保持する。表示生成失敗を取得失敗へ置換しない。説明をnative本文に保持したうえで表示要点を整え直す。型の修正や再生成のために実務を再収集しない。

HTMLはlight/darkの表示設定に応じて文字と背景を対で切り替え、ブラウザー標準のcolor-schemeでiframeのthemeにも追従する。フォーム・状態バッジ・リンク・境界も同じ配色に揃え、印刷時はlightで表示する。

## hostへの保存

hostの送信容量に応じてMarkdownを行境界で順序付きpartへ分ける。固定件数で内容を省略しない。全partとreport.json・report.htmlを保存し、UTF-8 byte列のsha256を計算する。簡単なhandoff JSONへreport_date・timezone・information_scope・destination（configの保存先）・parts（order/path/sha256）・artifacts（JSON/HTMLのpath・bytes・sha256）・未完成partや未完了作業・delivery_statusを記録する。本文生成時のdelivery_statusはhost-handoff-pending。薄い表示用JSONの型検査を、取得・分析・評価や台帳完成のgateにしない。

連携可能なhostへ全Markdown本文・JSON・HTMLとhandoffを渡す。設定の親配下へ本人限定など許可された閲覧範囲でYYYY-MM-DD スキル振り返りを保存する。同日既存ページは日付・scope・親を確認し、重複を避けて追補する。Pageはraw HTML本文にせず、対応hostのcreate_page_visualizationでsandbox HTMLをupload・embedし、説明・根拠はnative本文へ保存する。既存本文を消さず、内部handoff情報をページ本文へ転記しない。別site・backendや新しい接続・アクセス拡大は不要。

hostは全part・artifactsのdigestと読戻し結果、HTML embedの結果を別々に照合し、保存先URL・saved/verified/delivery-held・不一致理由を最小receiptで返す。receiptを非公開出力rootへ保存する。未確認なら確認待ち、失敗なら再送可能な本文と理由を残す。通知と毎日のレポート生成・保存は別であり、変更なしでもレポートを残す。
