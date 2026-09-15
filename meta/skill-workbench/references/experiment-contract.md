# 実験データと CLI

Python 3.11+ と Codex CLI を使う。補助コードは[workbench.py](../scripts/workbench.py)、入力例は[examples](../examples/)にある。
診断と編集の生成、匿名比較、採否判断は agent が担当する。CLI は snapshot・実行・採点保存・比較・診断保存・閲覧を担当し、自動でモデルを改善し続けたり、正本を書き換えたりしない。

## 保存単位

実験領域は公開 repository と snapshot 元の外へ置く。実務の生ログは配布する skill に含めない。

```text
experiment/
  candidates/<sha256>/candidate.json   親・仮説・構造とファイル digest
  candidates/<sha256>/files/           runtime bundle の全ファイル
  runs/<run-id>/suite.json             評価の版
  runs/<run-id>/environment.json       実行条件
  runs/<run-id>/prompt.txt             実行担当へ渡した入力
  runs/<run-id>/trace.jsonl             Codex の実行イベント
  runs/<run-id>/workspace/              実行後の成果物
  runs/<run-id>/answer.txt              最終応答（取得できた場合）
  runs/<run-id>/run.json                実行状態・測定値・artifact digest
  runs/<run-id>/grading.json            独立した採点と証拠
  diagnoses/<sha256>.json              train の診断・反証・更新方向
```

候補 ID はファイル内容・実行属性・親・仮説・構造の digest。親は複数指定できる。script と近接 skill を含め、比較対象となる runtime bundle 全体を保存する。
再開時は candidate.json を索引として、strategy、親、比較レポートのケース別結果から次の親を選ぶ。
既存の候補、採点、比較出力は上書きしない。再実行は新しい run ID を作り、同じ反復番号のどの試行を比較に使うか明示する。
不採用案も親として再利用できる。digest は偶発的な変更の検出であり、悪意のある改変に対する署名ではない。

## Runtime bundle と fixture

bundle は試行 workspace に展開する相対パスの木である。単一 skill の Execution ならルートの SKILL.md と参照資料を保存できる。
Discovery や連鎖を試す場合は `.agents/skills/<name>/SKILL.md` という配置と、必要な近接 skill を含める。
AGENTS.md や設定も変更対象なら bundle に含める。ユーザー repo 全体を無条件に snapshot しない。
fixture は変更しない初期ファイル。試行ごとに一時ディレクトリへ複製し、その上へ bundle を重ねる。同一パスは bundle が優先する。
skill なしの候補は metadata で `without_skill: true` を明示し、その skill が fixture にも存在しない構成で作る。Execution の入口が欠落した通常候補はエラーにし、暗黙に skill なしへ切り替えない。
source と fixture の symlink・特殊ファイルは受け付けない。生成された symlink はリンクのまま成果物として保存する。

## JSON の契約

入力の構造、ID、重複、列挙値、根拠の必須条件は CLI が検査する。未取得の数値は null とし、ゼロにしない。

- candidate metadata：[candidate.json](../examples/candidate.json)。`parents` は候補 ID の配列、`hypothesis` は今回の仮説、`strategy` は構造を区別する短い説明。任意の `without_skill` は boolean（既定 false）。同じ suite のまま skill なしの比較を明示する。
- suite：[suite.json](../examples/suite.json)。`version: 1`、`mode: execution | discovery`、`entrypoint` は相対ファイルまたは null、`cases` は空でない配列。
- case：`id`、`prompt`、`split: train | validation | test`、`checks`。
- check：`id`、成果を判定する `criterion`、退行を採用不可とする `required: boolean`。
- config：[config.json](../examples/config.json)。`model`、`reasoning`、`context` は空でない文字列。任意の `disabled_skills` は評価プロセスで無効にする既設 SKILL.md の絶対パス配列（既定は空）。
- grading：[grading.json](../examples/grading.json)。`grader` と、チェック ID ごとの `verdict: pass | fail | unknown`・空でない `evidence`。すべてのチェックに判定が必要。
- diagnosis：[diagnosis.json](../examples/diagnosis.json)。仮説・scope・`status: active | refuted`・support/counterevidence の run ID・directions。各 direction は `operation: add | delete | replace | move`、`layer: metadata | body | reference | script | configuration`、相対 `path`、`reason`。

case/check/run の ID は英数字・`_`・`-`。候補と suite の比較には全体の SHA-256 を使う。ケース追加・分割変更・採点基準変更も suite の別版になる。
diagnosis は採点済みで正常終了した train 実行だけを根拠にでき、validation/test の結果を momentum へ流し込めない。
否定された仮説は `refuted` として新しく保存する。同じ仮説の古い active 記録も残るため、更新担当は反証側も検索する。

agent が書く proposal には親 ID、診断 ID、編集予算、対象パス・層・操作・理由、検証すべき仮説を記録する。
decision には候補 ID、比較レポート、採用・保留・棄却、理由、未確認事項を記録する。これらの意味的判断は CLI が代行しない。

## 実行例

次の値は利用する絶対パスへ置き換える。`CANDIDATE_ID` と `RUN_PATH` は各コマンドの出力をそのまま使う。
`config.json` のモデルは利用環境で実際に使う ID に置き換え、推論設定と context を記入する。

```sh
python3 /path/to/skill-workbench/scripts/workbench.py snapshot \
  --archive /private/experiment --source /private/bundle --metadata /private/candidate.json

python3 /path/to/skill-workbench/scripts/workbench.py run \
  --archive /private/experiment --candidate CANDIDATE_ID \
  --suite /private/suite.json --case ordinary --fixture /private/fixture \
  --config /private/config.json --repeat 1 --timeout 600

python3 /path/to/skill-workbench/scripts/workbench.py grade \
  --run RUN_PATH --grading /private/grading.json

python3 /path/to/skill-workbench/scripts/workbench.py remember \
  --archive /private/experiment --diagnosis /private/diagnosis.json

python3 /path/to/skill-workbench/scripts/workbench.py compare \
  --suite /private/suite.json --runs BASELINE_RUN CANDIDATE_RUN \
  --baseline BASELINE_ID --candidate CANDIDATE_ID --split train \
  --output /private/comparison.json

python3 /path/to/skill-workbench/scripts/workbench.py report \
  --runs BASELINE_RUN CANDIDATE_RUN --comparison /private/comparison.json \
  --output /private/review.html
```

例の ordinary は train である。候補選択を確認するときは counterexample を実行し、そのチェックで採点して `--split validation` を指定する。
run は一ケースずつ実行する。agent が予算内で候補・ケース・反復を選び、同じ反復番号の対を揃える。
run は記録を保存できれば終了コード 0 を返す。評価実行の成功は `run.json` の `status` で判断する。
`status: completed` は CLI が正常終了し最終応答を取得したという意味だけであり、課題の合格ではない。
採点担当は run folder を読んで grading を作る。採点の変更は元の grading を消さず、別の評価実験で行う。

## 比較とレポート

比較は同じ suite・environment・case・repeat の対を使う。選択した run ID と採点込みの digest を保存し、レポートでも同じ実行を渡したことを検査する。異なる環境や重複した試行はエラーにする。
未実行ケース、対の欠落、実行障害、未採点、unknown は判定不能として残す。
counts はチェック×反復の観測数であり、タスク成功率や統計的な有意差ではない。ケース別の rows を見る。

- `regressed`：必須チェックで pass → fail がある。
- `inconclusive`：判定不能がある。
- `tradeoff`：必須以外に退行がある。
- `improved`：退行・判定不能がなく、fail → pass がある。
- `unchanged`：既知の判定がすべて同じ。両方 fail も含むため、採用可能を意味しない。

metrics は正常終了した対の平均差。いずれかの測定が欠けた指標は null。品質同等や有意な費用削減を自動判定しない。
HTML は応答・記録・比較結果を表示し、成果物フォルダへのリンクとコメントの JSON export を提供する。
このレポートは候補 ID を含む。匿名比較には別途ラベルを伏せた成果物だけを比較担当へ渡す。
出力形式ごとの画像化・Office rendering は行わない。必要な viewer で実物を確認する。

## 実行環境と限界

Codex CLI 0.154.0 のローカル help にある `exec --json --ephemeral --ignore-user-config --skip-git-repo-check` を使用する。
モデル・推論設定を明示し、`workspace-write` と `approval_policy="never"` で新しいプロセスを起動する。
ユーザー設定を読み込まないため、この adapter は任意の MCP・profile を使った評価には対応しない。必要なら adapter を明示的に拡張し、別環境として比較する。

fixture、CLI version、adapter のソース digest、disabled_skills は自動記録する。`context` には適用される上位指示、global skill catalogue、tools、外部状態の版または digest を記入する。
`disabled_skills` は [公式の skills.config](https://learn.chatgpt.com/docs/build-skills#enable-or-disable-local-codex-skills) を `-c` で評価プロセスだけへ渡し、ユーザーの設定を書き換えない。重複した配置先があれば各パスを指定する。
ignore-user-config は全 skill・上位指示・環境変数の隔離を保証しない。グローバルで入った対象 skill が baseline に混入していないか、実行 trace と catalogue を確認する。
変更対象 skill を除いた専用環境を使えない Discovery は未検証と報告する。同じ context 文字列を書くだけで実際の同条件が保証されるわけではない。

採点用 suite と診断は実行プロンプトへ渡さず、一時 workspace の外に置く。ただし read 権限の分離は保証しない。
機密の holdout や外部書き込みを伴う課題には、別 OS 環境・専用アカウント等の実行隔離が必要になる。
