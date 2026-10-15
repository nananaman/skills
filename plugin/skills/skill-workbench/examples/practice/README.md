# 実務の完成品質を確かめる合成課題

既存の [workbench.py](../../scripts/workbench.py) に渡す suite と fixture。
新しい比較器、実サービスへの接続、導入変更は必要ない。
実務から挙げられた失敗の種類を合成しており、私的な入力や実行履歴を含まない。
既存の [suite.json](../suite.json) が扱う「単発の観測から規則を一般化しない」課題とは別の成果を測る。

## 課題と完成条件

| case ID | split | 作るもの・確かめるもの | 完成を示す証拠 |
| --- | --- | --- | --- |
| pr-purpose-and-pending | train | 問題と変更後の挙動、確認済みと未実施が分かるPR文案 | `output/pr.md` と変更資料。タイトルと冒頭でもマージだけでは解決しない範囲が分かる |
| verify-final-edit | train | 表示文言の変更と両分岐のテスト | 最終ファイル、最後の関連編集より後に成功したテストの記録 |
| api-test-contract | validation | 既存APIと食い違うテストの修正 | 公開シグネチャと意味を保つ差分、削除・skipしていないテストの成功 |
| long-screen-labels | test | 長い日本語・空白なし英語ラベルを読める画面 | 最終HTMLの360px/1280pxでの描画、件数と棒の対応、キーボード操作の確認 |

ケースごとの細かい判定は [suite.json](suite.json) にある。
`selection-*` はDiscoveryの観測、それ以外は成果の品質。必須品質の失敗を起動成功で相殺しない。
traceで実際のskill読取を確認し、自己申告・単なる名前の列挙を起動成功にしない。
対象skill名やその本文パスは課題promptへ足さない。入力・出力のファイル指定は通常の依頼として残す。UIの描画toolがない場合は静的確認の範囲を残し、視覚条件を `unknown` とする。

公開ケースのため、秘密のholdoutとは扱わない。ここにあるvalidation/testを改訂の原因分析に使ったら、
新しいsuite版でtrainへ移す。同じ元タスクの言い換えを別splitの独立例に数えない。
この小さな課題群の結果を実務全体の改善実証へ広げない。

## 既存CLIで実行する

以下はrepository rootから実行する。`EXP` は公開repositoryの外にある新しい私的な実験ディレクトリを指定する。
`SOURCE` は比較する版のcheckout。候補ごとに別bundleを作る。
通常のskill配置を使い、実行promptへの手動SKILL読取リストは追加しない。

```sh
PRACTICE="$PWD/plugin/skills/skill-workbench/examples/practice"
WORKBENCH="$PWD/plugin/skills/skill-workbench/scripts/workbench.py"
EXP=$(mktemp -d /private/tmp/skill-practice.XXXXXX)
chmod 700 "$EXP"
SOURCE="$PWD"
export EXP SOURCE
python3 - <<'PY'
import json, os, shutil
from pathlib import Path
exp, source = Path(os.environ['EXP']), Path(os.environ['SOURCE'])
bundle = exp / 'bundle'
for skill in (source / 'plugin/skills').iterdir():
    if skill.is_dir():
        # 採点用のsuiteを実行workspaceへ持ち込まない。
        shutil.copytree(skill, bundle / '.agents/skills' / skill.name,
                        ignore=lambda path, names: ['practice'] if
                        Path(path) == skill / 'examples' and skill.name == 'skill-workbench' else [])
metadata = {'parents': [], 'hypothesis': '現行版の探索的な完成品質確認',
            'strategy': '通常のcatalogue配置、課題名で起動を誘導しない'}
(exp / 'candidate.json').write_text(json.dumps(metadata, ensure_ascii=False))
PY
CANDIDATE_ID=$(python3 "$WORKBENCH" snapshot --archive "$EXP/archive" \
  --source "$EXP/bundle" --metadata "$EXP/candidate.json")
```

[config例](../config.json) を `$EXP/config.json` にコピーし、実際に使えるモデル・推論設定を記入する。
`context` に上位指示、catalogue、tools・描画環境の版またはdigestと外部状態を残す。
実験中にそれらが変わったら別の比較にする。fixtureのdigestとCLI版は自動記録される。

既設skillが評価bundleに重なる場合は、`disabled_skills` に既設の各 `SKILL.md` の絶対パスを指定し、
評価プロセスだけで無効にする。plugin cacheと通常配置の重複も調べる。
既設skillの削除・install・ユーザー設定の書換えはしない。無効化とcatalogueを確認できないときは、
Discoveryを未検証とする。`--ignore-user-config` だけで隔離を保証しない。
通常AGENTSを使った環境と、専用評価環境で上位指示を固定した環境も混ぜない。

```sh
RUN_PATH=$(python3 "$WORKBENCH" run --archive "$EXP/archive" \
  --candidate "$CANDIDATE_ID" --suite "$PRACTICE/suite.json" \
  --case verify-final-edit --fixture "$PRACTICE/fixture" \
  --config "$EXP/config.json" --repeat 1)
```

他のcaseも同じfixtureを使い、毎回新しいworkspaceへ複製する。`api` の初期テストは
公開契約にない引数を使って失敗するのが正しい初期状態。`verification` の初期テストは成功する。
依頼の編集範囲はcaseで指定した範囲に限定する。PRケースは入力を変更せず `output/pr.md` を新規作成し、ほかのcaseはそれぞれの対象フォルダ内を編集する。初期状態の別caseの失敗を今回の失敗と数えない。

Executionだけを調べる場合は、suiteを実験領域へ複製し `mode` を `execution`、`entrypoint` を
対象の `.agents/skills/<name>/SKILL.md` にする。起動チェックは品質チェックと分けて扱う。
その結果をDiscoveryの証拠へ転用せず、元のsuiteとの比較もしない。

## 採点と同条件比較

新しい文脈の採点担当へ課題、suiteのcheck、最終成果物、必要なtraceを渡す。
編集意図、候補の新旧、期待する勝者は渡さない。主担当だけで確認した場合は自己確認と明記する。
[grading例](../grading.json) と同じ構造で、このcaseの全checkに `pass | fail | unknown` と
具体的なファイル・trace上の証拠を付けて `$EXP/grading.json` に保存する。

```sh
python3 "$WORKBENCH" grade --run "$RUN_PATH" --grading "$EXP/grading.json"
```

評価器の較正には [calibration.md](calibration.md) の良い例・悪い例を採点する。
これを実行担当へ渡さない。実際のskill比較とは別の、採点条件が欠陥を見逃さない確認である。

比較する版をそれぞれsnapshotし、suite・fixture・model・reasoning・tools・上位指示・反復番号を揃える。
同じ反復番号に複数試行がある場合、採用したrun IDと除外理由を残す。
skillなしを対照にするなら、対象をbundleとfixtureから外してmetadataの `without_skill: true` を指定し、
同じ無効化設定を両候補に適用する。近接skillやglobal配置からの混入も確認する。

```sh
python3 "$WORKBENCH" compare --suite "$PRACTICE/suite.json" \
  --runs "$BASELINE_RUN" "$CANDIDATE_RUN" \
  --baseline "$BASELINE_ID" --candidate "$CANDIDATE_ID" \
  --split train --output "$EXP/comparison.json"
```

この例のtrainには複数caseがある。対応する全runを `--runs` に並べる。
一部だけ実行した場合、欠けたcaseはCLIが `unknown` とする。
CLIの総合assessmentは起動checkも含むため、品質改善は品質checkのcase別結果から判断する。
選択の成否、品質、時間・token、やり直しを別々に報告する。起動checkの証拠には実際に読んだskill/resourceの一覧を残し、関連する別のskillを選んだだけで不合格にしない。

[observation-template.json](observation-template.json) をrunごとに実験領域へコピーして記録する。
`grading_file` で全checkの原票を参照し、`selection_check_ids` と `quality_check_ids` にこのcaseのIDを漏れなく列挙する。
品質の総合判定は必須品質checkにfailがあればfail、failがなくunknownがあればunknown、すべてpassならpassとする。
任意の品質checkは個別に報告し、必須checkの退行を相殺しない。
CLIの `duration_seconds` は実行プロセスの壁時計時間、`tokens` は取得できたinput+outputの合計で、
人の採点時間や料金ではない。やり直しは「完了とした成果の不備を理由に再依頼して直した回数」とし、
実行中の通常の編集・TDDで意図した初期失敗や環境障害の再実行とは分ける。
全履歴が確認できた場合だけ0を記録し、履歴がない場合は `null` と不足理由を残す。
対が欠けた指標を推測で埋めたり、文字数をtokenへ変換したりしない。

実行障害・timeout・未採点・成果不合格を区別する。記録保存の終了コード0や
`status: completed` は合格を意味しない。生ログ・私的情報は実験領域へ保管し、
公開PRには合成ケースと秘匿情報を除いた集計・制約だけを載せる。
候補数・実行回数の上限はここで追加しない。成果を満たした、追加比較が判断に寄与しない、
実行環境や利用上限の制約に達した、のいずれで止めたかを残す。
