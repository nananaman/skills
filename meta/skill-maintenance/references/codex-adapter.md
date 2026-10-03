# Codex の読み取りアダプタ

## 取得元と限界

[公式 app-server プロトコル](https://developers.openai.com/codex/app-server/)と、installed CLI 0.159.3 の生成JSON schemaを根拠にする。非公開SQLite/JSONL形式は使わない。新しいdaemonを起動せず、既存daemonへの`codex app-server proxy`のみ使う。proxyは生バイト転送なので、同じ経路でWebSocket HTTP Upgradeを行い、JSON-RPCをmasked text frameへ載せる。UnixソケットへJSONLを直接送らない。frame/HTTP headerの上限・Upgrade acceptance・分割message・pingを検査する。CLI版は0.159.3に照合する。initialize応答のCodex userAgent版は、0.159.3のexport契約と[0.160.0のmetadata限定契約](codex-0160.md)を区別して選び、未知版・不明な形式ならthread読取前に停止する。RPC拒否、履歴ページの非対応、未知の必須形式では停止する。experimental APIなので、版更新時はfixture・schema・接続検証を改めて行う。

source設定に`thread_ids`の非空・重複なしallowlistがある場合、`thread/read includeTurns:false`でそのIDだけを直接読む。`thread/list`や対象特定の検索は行わず、存在しないID・返却IDの不一致・範囲外cwdで停止する。別IDの祖先も勝手に取得しない。必要な祖先が指定ID集合に含まれなければ停止する。このモードは指定ID集合だけのcoverageであり、明示除外IDもunits空配列のmetadata headerを保持して集合一致を検査する。除外IDのturnや本文を読み込まない。過去24時間の全セッションを集めたとは報告しない。source_idとstateはこの限定scope専用にし、他rootやsourceの記録を含むstateはprepareが拒否する。取得mode・ID集合・sourceのrepo/cwd/scope・transportをstateへ固定する。既存stateからID設定を外して一覧取得へ拡大したり、同じrootのchildだけを追加・削除したりする変更も、RPC前に拒否する。変更時は対象・再収集開始時刻を明示した専用stateを用意し、既存の反映結果との重複も照合する。実際のthread ID対応を確認できない場合も、一覧取得へfallbackしない。

`thread_ids`がない場合の`thread/list`はcwdの完全一致allowlist、unknownを含む全対応sourceKinds、archivedの両方をページ取得する。`useStateDbOnly:true`で索引修復を避ける。対象は**この端末のapp-server索引に登録されたスレッド**であり、全ローカルrollout・他端末・クラウドの網羅性は表明しない。日次運用に使う前に、対象開発環境の記録がこの索引に載ることを確認する。載らない記録を無視して全セッション収集成功とは扱わない。

`thread/turns/list itemsView:notLoaded`で古い未完了も含むturnメタデータを列挙し（itemsは省略または空配列を受け付け、本文があれば停止）、期間内の完了turnと前回持越しだけを`thread/items/list turnId`で読む。ページ不足・予算不足は部分成功にしない。fork/ephemeralや取得できない祖先は停止する。明示除外rootと子孫の本文は読まず、`--current-root`は以後の状態へ保存する。過去の保守・評価rootも初回source設定に入れる。識別できない実験を独立した成功の証拠にしない。

保存するのはtext userMessageと`phase:final_answer`のagentMessageだけ。tool出力・reasoningは保存しない。expectedは元依頼から評価条件を導くためのラベルで、成功や独立検証を捏造しない。既知の秘密形式を検知したturn、画像等の非text依頼、final判別不能は停止する。秘密検知regexは漏えい防止の保証ではない。source repoと情報scopeの事前限定、非公開保存、agentによる公開差分確認を必要とする。金融・雑談・他組織のスレッドをsource設定へ含めない。

取得前後のthread ID・時刻・祖先が変われば停止する。APIは一貫したsnapshotを保証せず、秒内の同時更新も検出できないため、非稼働時間での試行を推奨する。coverageは索引の全ページを取得した範囲の表明。索引外記録や未検知の同時変更の網羅性は保証しない。

送信pipeのbackpressureを含め、HTTP Upgradeと各RPCには30秒の期限を設ける。期限切れの回収対象は自分が起動した一時proxy子processだけであり、既存daemonを終了・再起動しない。RPC通知を固定件数で打ち切らず、bounded queueと期限で制限する。server-initiated requestや非objectのRPC応答は実行せず停止する。版番号のsuffixも一致とは扱わない。

## 読み取り前提とnotLoaded

取得済み0.159.3 schemaの`ThreadStatus.notLoaded`は正常なruntime statusの一つであり、保存済みthreadの不存在を示す値ではない。公式仕様の`thread/read`はstored threadをresumeせず読み、`includeTurns:false`ではsummaryだけを返す。ロードを必須の前提とする契約はない。

RPCエラーの文字列`thread not loaded`は、そのサーバーが指定IDのreadを受理できなかった事実を示す。正常応答の`status.type:notLoaded`とは別物であり、IDが不存在・別サービスのID・未ロードのどれかをこの文字列だけで確定しない。UIで対象を開くことが解決になる保証もない。`thread/resume`等で状態を変更して取得可能にする操作は読み取り契約に含めない。

本文を読む前に、次を確認する。

- 承認した作業のIDが、接続先のローカルCodex thread IDと直接対応すること。タイトルや別サービスのtask IDから対応を推測しない。
- 元のCODEX_HOME・既存daemonに当該記録があり、同じ許可範囲で読めること。データ探索で不足を埋めない。
- CLIとinitializeのCodex userAgent版が検証した組合せ・methodの範囲に一致し、応答codexHomeが固定した実効CODEX_HOMEと一致すること。UIでthreadを開いても版の停止条件は解消しない。別版対応にはその版のschemaと検証を必要とする。
- 返却ID・cwdが承認済みallowlistと一致し、祖先も必要なら指定済みIDだけで揃うこと。
- 保存履歴のturn/itemsページAPIに対応し、完了・時刻・全ページを確認できること。APIのunsupported、未記録の時刻、完了不明は未収集にする。

実環境の診断記録は非公開の作業データへ残し、これら前提を満たす証明としてfixture成功を使わない。未ロードエラーを受けた後に同じ待機を反復したり、一覧・resume・別保存形式へfallbackしたりしない。

## 一度だけ設定する値

[codex-source.json](../examples/codex-source.json)の`fixture`設定は合成専用。実運用は`transport:proxy`にし、fixtureキーを除く。1件の限定試行では`thread_ids: ["承認済みの対象ID"]`とし、max_threadsも1、max_content_turnsは1〜3を指定する。対象のcwdはsource repo allowlistとの一致を確認する。許可された取得方法でcwdやIDを確認できなければ、他の一覧や本文検索で探さず停止する。source_idは端末・索引を区別する安定ID。reposに許可された開発repoのID、絶対cwd、targetと同じinformation_scopeを指定する。cwdはrepoルート完全一致なのでworktree等は別エントリを明示する。

`path_flavour`はposix/windows。path操作はpathlib、CODEX_HOMEは設定`codex_home`、次に環境変数、未指定なら実行ユーザーの`.codex`へ固定する。実効CODEX_HOMEと解決したCLI起動path、fixtureではsource設定から解決した実体pathをstateへ固定し、変更時は読取前に停止する。元の入力元・既存台帳との照合なしに専用stateで再収集しない。ホームやMacパスをコードへ固定しない。Windowsはpath fixtureのみ確認し、実際のproxy接続は未検証。`codex_executable`は信頼するCLI起動名／絶対path。これら設定は実行対象を選ぶので、ログ・外部コンテンツから生成して信用しない。

max_threads/max_turnsは全メタデータ取得の上限、max_content_turnsは本文取得回数の上限、max_itemsは各turnのitem上限。最初の実データ試行はmax_content_turnsを1〜3にし、静かな対象repoを限定する。期間内にそれ以上あるなら停止し、無断で上限を増やさない。台帳checkpointより取得開始を戻し、休止中の取り逃しと未完了を回収する。source IDを変えて再読込しない。

## 一回の起動

agentへの依頼例：`$skill-maintenance 指定target/source設定を使って24時間を分析・評価まで実行。編集・Git外部操作はしない。` agentは現在のroot IDを得て次を一回実行し、返されたbatchでretrospective-codify→候補がある場合だけskill-workbenchへ進む。export/判断JSONの手整形をユーザーの定例作業にしない。record用判断JSONは分析agentが根拠付きで作る。

```sh
python3 meta/skill-maintenance/scripts/maintenance.py prepare --source meta/skill-maintenance/examples/codex-source.json --target meta/skill-maintenance/examples/target.json --repo . --state ../maintenance-private/state.json --output ../maintenance-private/batches --current-root fixture-maintenance --cutoff 2026-01-03T00:00:00Z
```

これは合成fixtureの一回起動。実運用では一度検証した非公開設定・実際のcurrent rootへ置換し、cutoffは省略できる。prepareはモデル・スキル改善・Git操作を実行しない。読取拒否後は同じ実行中に別取得経路へ切り替えない。CLIがblockedなら分析を開始せず、その端末の接続・取得確認を未完了として報告する。
