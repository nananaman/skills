# 日次レポートと保存

callerのreport-config.jsonからtimezone・information_scope・保存先を解決する。日付はそのtimezone基準とし、取得期間と区別する。入力の情報scopeと保存先の許可範囲を照合する。匿名化だけで別scopeへの転記を許可しない。

毎回、Git外の新しい非公開fileへMarkdownを作る。対象実務ごとに、分かる作業名、入力元、観測/自己申告、取得状態、結果、学び、未確認事項を記す。対象期間、全対象/取得/振り返り/失敗/残件、開始・終了時計と処理全体のwall time、段階別実測時間、改善候補と根拠、検証と限界、採否と理由、PR、残課題を含める。候補なしと未分析、取得失敗と対象なしを区別する。

秘密、生ログ、原文引用、推論、私的絶対path、内部ID・cursor・運用情報を載せない。私的な作業名はユーザーが分かる短い内容へ一般化する。公開PRのURLは使える。本文全体を証拠と照合し、privacy検査も行ってからhostへ渡す。自動regex検査だけで秘密がないとは証明しない。

hostの送信容量に応じてMarkdownを行境界で順序付きpartへ分ける。固定件数で内容を省略しない。全partを保存し、UTF-8 byte列のsha256を計算する。簡単なhandoff JSONへreport_date・timezone・information_scope・destination（configの保存先）・parts（order/path/sha256）・未完成partや未完了作業・delivery_statusを記録する。本文生成時のdelivery_statusはhost-handoff-pending。厳格な本文JSON schemaや台帳完成を生成の前提にしない。

連携可能なhostへ全Markdown本文とhandoffを渡す。設定の親配下へ本人限定など許可された閲覧範囲でYYYY-MM-DD スキル振り返りを保存する。同日既存ページは日付・scope・親を確認し、重複を避けて追補する。内部handoff情報をページ本文へ転記しない。新しい接続やアクセス拡大は行わない。

hostは全part・digestと読戻し結果を照合し、保存先URL・saved/verified/delivery-held・不一致理由を最小receiptで返す。receiptを非公開出力rootへ保存する。未確認なら確認待ち、失敗なら再送可能な本文と理由を残す。通知と毎日のレポート生成・保存は別であり、変更なしでもレポートを残す。
