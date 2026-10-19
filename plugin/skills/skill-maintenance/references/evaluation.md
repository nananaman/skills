# 再開可能な比較と独立した採用判断

選んだ候補だけを既存の [workbench](../../skill-workbench/references/experiment-contract.md) へ渡す。
取得・一次振り返り・ガイド確認の全対象一覧と再開位置は既存の state に保持し、
比較用の上限をその処理へ適用しない。以下の台帳は比較だけを扱い、日次取得や振り返りを代行しない。

## ケースを準備する

実務の観測と公式ガイドの推奨から、変える判断と成果で検査できる仮説を作る。
公開可能な fixture へ縮約し、秘密・生ログ・元の内部 ID を除く。縮約時に失われる条件も記録する。
実務由来の合成 fixture は実環境の再実行ではない。想定例だけの成功で実スキルの改善を主張しない。

同じ実務の親子・言い換え・近似例には同じ family を付け、train / validation / test をまたがせない。
成功例と失敗例、通常処理を壊さないケース、誤った成功報告を検出する必須 check を含める。
チェックは正解の語句への一致ではなく、成果物・模擬外部ツールの状態・実行記録と報告の一致を判定する。
採点器は既知の良い出力、悪い出力、証拠不足の出力で校正する。

提案・編集担当には train の必要な観測だけを渡す。採点用正解・validation/test の詳細は渡さない。
最終確認は、選択済みの候補に対し、その候補の編集・選択に使わなかった family で行う。
過去の候補や別 campaign で使った事例も非公開の履歴と照合する。台帳は family の意味的重複や過去の未知の使用を検出しない。
最終確認の失敗を編集に使う場合はその family を開発用へ移し、新しい最終確認を用意する。

## 既存実行 host へ接続する

[campaign.py](../scripts/campaign.py) はモデル実行器ではなく、workbench の run を受け取る比較台帳。
[plan の合成例](../examples/campaign.json) を非公開領域へコピーし、候補 ID、suite、family、根拠、
実際の環境 digest、今回許可された予算を記入する。過去候補の予算を流用せず、未指定なら budget は `{}`。
CLI は新しい campaign directory を作る。既存の target/source/state/report-config は変更しない。

実行 host は、本番の鍵・元ログ・採点用正解が実行側から読めない限定環境を用意し、
模擬外部ツールだけを接続する。モデル・推論設定・fixture・上位指示・tool・評価器を固定し、
workbench の environment.json の digest を plan.environment へ設定する。
通常の AGENTS と .agents/skills の検出を使い、起動 prompt に手動の SKILL 読込一覧を追加しない。

新しい会話や ignore-user-config、workspace-write だけではファイルの読取や認証情報の隔離は証明できない。
CLI の認証用設定を丸ごとコピーしない。既存の sandbox・承認・通信制約を維持し、
隔離が成立しないときは比較を保留して、対象・不足条件・必要な上限を返す。
基盤の mock テストを LLM 改善の代替にしない。

```sh
python3 <skill-root>/scripts/campaign.py create --campaign <private/new-campaign> --plan <private/plan.json>
python3 <skill-root>/scripts/campaign.py claim --campaign <private/campaign> \
  --candidate <candidate-id> --case <case-id> --repeat 1 --timeout <authorized-seconds>
# host が返された claim ID を保存し、既存の限定実行経路で一ケースを実行・独立採点する。
python3 <skill-root>/scripts/campaign.py finish --campaign <private/campaign> \
  --attempt <claim-id> --run <private/workbench-run>
python3 <skill-root>/scripts/campaign.py summary --campaign <private/campaign>
```

claim は単一の同時実行枠を永続予約する。同じ候補・ケース・反復の再送を拒否する。
max_runs は中断・障害も消費し、max_seconds は各 claim の timeout 全量を予約する。
実測が timeout を超えたらその実測を請求時間に使い、採用ゲートを止める。
時間上限を実行時に守るのは host の責務であり、この台帳自体はプロセスを起動・停止しない。
トークン・金額の硬い上限がある場合は対応する host limiter が必要。この版はそれらの予算を受けると作成を拒否する。
予算を削除して回避せず、接続未対応として返す。

中断で running が残った場合、先に host が同じ処理の生存と外部状態を確認する。
未確認のまま interrupt や再送を行わない。停止を確認した根拠付きで次を実行し、
障害・timeout・中断が一つでもある campaign の採用は保留する。必要な再比較は新 campaign に分け、旧 campaign との関係と、元の残予算から引き継ぐ上限を記録する。新 campaign 作成を予算のリセットにしない。旧 campaign では独立したケースの評価・回収を続けられるが、後の成功で障害を消さない。

```sh
python3 <skill-root>/scripts/campaign.py status --campaign <private/campaign>
python3 <skill-root>/scripts/campaign.py interrupt --campaign <private/campaign> \
  --attempt <claim-id> --evidence '<private stopped-process and side-effect evidence>'
```

台帳は file lock と atomic replace で同時更新を直列化し、state と親 directory を fsync する。運用は同じローカル filesystem に限る。
import 後の run・grading の変更は digest 不一致で止め、別 campaign で再評価する。
status の内部 ID・私的 path・根拠全文を公開レポートへ転記しない。

## score から採用を分離する

summary はケースごとの対応比較、必須条件によるタスク成功数・成功率、誤った成功報告数、
正常ケースの悪化 check 数、時間・token・費用を返す。未採点、unknown、実行障害、未実行を成功へ数えない。
費用の取得ができなければ null。現行 Codex adapter は請求額を取得しない。
時間・token の単発差を統計的改善や費用削減へ一般化しない。

編集担当とは別の文脈で validation を評価した担当が、summary の evidence_digest と根拠を指定して選択する。
reviewer ID の違いは記録であり、CLI が文脈分離を証明するものではない。
選択後は train/validation の追加実行を凍結し、approve の場合だけ test を開始する。

```sh
python3 <skill-root>/scripts/campaign.py select --campaign <private/campaign> \
  --reviewer <independent-reviewer> --decision approve --evidence-digest <summary-digest> --reason '<reason>'
# 未使用 test の両候補を claim / 実行 / 採点 / finish し、新しい summary を読む。
python3 <skill-root>/scripts/campaign.py gate --campaign <private/campaign> \
  --reviewer <independent-reviewer> --evidence-digest <final-summary-digest> --reason '<final-review>'
```

gate は全 split の対が揃い、重要な成果がすべて pass、退行・判定不能がなく、
train/validation に観測された品質改善があり、独立した判断が入力された場合だけ eligible_for_draft を記録する。
両候補 fail の同点、平均 score による退行の相殺、古い証拠の判断は受け付けない。
負担だけを減らす候補は別途、成果同等と対応する負担測定を独立評価する。この品質改善ゲートに合わせて要求を変えない。
gate 確定後は追加試行を凍結する。正常終了・gate 成功は採用・導入・merge の実行ではない。静的に許可された基盤整備の Draft PR は効果未検証のまま作れるが、
評価成功と表現せず、実スキル改善候補の採用とは区別する。

掲載は既存の report.json の reflections / checks / remaining を使い、比較回数・時間・欠測・
合成例か実環境か・独立判断・停止理由・未実施範囲を記す。生 trace を添付せず、固定 renderer へ渡す。
日次の対象全数・取得・振り返り・残件は既存台帳から別に集計する。

## Harness² から採る範囲

[公式 README（固定 commit）](https://github.com/google-research/harness2/blob/1cfe254e8d25b15f37048c3730134686abe60335/README.md)
の Propose–Probe–Compose と、採用済みの観測を次の改善へ戻す考え方を、既存 workbench の
候補 snapshot・比較・train 診断へ接続する。新しい optimizer や依存 package は導入しない。
公式 CLI は既定ベンチマーク向けで、Codex executor は sandbox 無効と明記されているため使用しない。
上流の deterministic demo・upstream tests・scripted adapter の成功は、この接続や LLM 改善の実証に流用しない。
