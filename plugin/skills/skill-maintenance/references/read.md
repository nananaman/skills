# 許可された実務を読む

## MacのCodex

本人が許可した端末と履歴pathだけを使う。通常は元CODEX_HOMEのsessions。特定fileだけの許可をdirectoryへ広げず、拒否を別端末・DB・reader・権限拡大で迂回しない。登録source repo、指定期間、回収済み対象、除外対象を確認して今回の対象を決める。metadataだけで絞れるscope外の本文は読まない。

明示的に許可されたfileまたはdirectoryへ直接readerを使う。各実行で改善先を--repoへ渡す。これは出力境界の検査であり、入力scopeを許可する引数ではない。

```sh
python3 <skill-root>/scripts/session_reader.py \
  --sessions <authorized-file-or-directory> --repo <improvement-checkout> \
  --source <private-source.json> \
  --output <new-private-directory-outside-git> \
  --since <inclusive-ISO-time-with-zone> --until <exclusive-ISO-time-with-zone>
```

source指定では先頭metadataで登録repoのremoteまたはcwd一致を確認し、scope外・指定除外root・子sessionの本文を読まない。子sessionを別の事例として数えず、親の結果から必要と分かった文脈は許可済みfileを個別に読む。metadata不明は取得失敗として残す。source省略は指定path全体の読取が明示許可された場合だけ使う。

期間省略なら指定pathの全履歴が対象。期間指定ではその間に活動のあるsessionを選び、以前の依頼も文脈として保持し、until以後の項目は含めない。cutoff付きで時刻不明の可視項目は出力せずpartialへ記録する。まず本文を出力しないindex走査で活動時刻と終了markerを確認し、最後がtask_startedなら進行中としてheldにする。中断は終了と作業成功を区別して振り返る。終了marker不明や壊れた終端はheldとして本文を出力せず理由を残す。index時点のbyte終端までを読んで、その後に追記された進行中の本文を出力しない。変更を検出したsessionの一時出力は破棄する。callerは保守・評価用か、管理scopeに入るかをmetadataと回収記録で判定する。読取は進行中本文を読む許可にならない。狭い一覧を作れない環境では取得不足として報告する。

manifestは全対象の読取結果・元fileとの対応・項目数・時間を持つ。session JSONLは元行番号付きの可視message・tool呼出/応答を1項目ずつ順番に書き出す。本文全体をメモリへ蓄積しない。metadata・対応repoと情報scopeはmanifestに残す。推論・encrypted_contentは除外し、エラー正規表現による要約やtool引数/応答の削除はしない。長いsessionは順番に必要な範囲へ分割して全範囲を読み、未読範囲を記録する。readerの生成成功はモデルが全範囲を読んだ証明ではない。

破損、読取中の更新、既知の元出力省略は当該sessionへ記録する。元の省略の検出は補助であり網羅的ではない。足りないtool結果や不明な終了状態も振り返りで注記する。読取完了を作業成功と推定しない。exit 1は失敗または部分取得があることを示し、取得できたsessionは引き続き使える。入力はcanonical pathを指定し、rootの親componentを含めsymlinkは追わない。root自体の不正は実行失敗、配下のsymlink候補は当該fileの取得失敗として記録する。出力directoryは新規作成し、既存fileを上書きしない。readerは既存state/checkpointや元履歴を更新しない。

## Workの自己振り返り

列挙・send/read能力のある許可済みhostが担当する。親へ委譲する場合も、対象scopeと取得結果を返す。正規のtask一覧を終端まで列挙し、許可された完了実務の全対象を安定した識別子で記録する。アカウント全履歴と可視範囲を混同しない。

既に回収済みの振り返りしか増えていないtaskは既存回答を使う。新しい実務があれば、そのtaskへ次の趣旨で依頼する。

> 元の依頼と制約、実行結果、重要な判断と根拠、有効だったこと・問題・教訓、未確認事項や改善案を振り返ってください。原因や修正先が不明でも観測事実を返してください。秘密・生ログ・内部情報は含めないでください。

各対象へ回収済み・失敗・未回収・進行中・除外と理由を付け、全対象が説明できるまで処理する。進行中へ依頼しない。自己振り返りの返信を新しい実務として再依頼しない。回答の形式・終了時刻・turn一致が不完全でも読める反省点を捨てず、不確実性を記録する。返答がない対象を変更不要へ置換しない。

親への最小引き渡しは対象一覧（内部ID・元実務/最新回収位置・状態）と回答本文、未回収/失敗の理由。固定envelope・schema・snapshot revisionは不要。IDや回収位置は非公開記録だけに保持する。
