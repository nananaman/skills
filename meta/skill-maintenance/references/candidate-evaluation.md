# 未検証候補の評価準備

この2候補は観測から作った仮説で、対象skillの不足が原因とは確定していない。create-plan / implementへの適用は行わない。実務のタイトル・ID・引用・秘密をfixtureへ移さず、以下は架空の入力である。

## 根拠資料の照合

まず指定資料・訂正・追加調査の食い違いが判断に影響するか、現行版とskillなしで比較する。通常Q&Aをcreate-planへ強制的に起動させない。計画依頼で現行版に不足が再現した場合だけ、対象と起動条件を確定する。
[evidence-suite](../examples/evidence-suite.json)は計画作成Executionの探索用。Discoveryを調べる場合は近接skillを含む実際のcatalogueで、通常Q&Aと計画依頼を分ける。候補の変更方向は既存の根拠確認の限定的な修正であり、外部資料への盲従や汎用Q&Aへの起動拡大を含めない。

## 呼出経路の契約確認

最初に対象repoの既存静的検査で不足を保証できるか調べる。指示追記より決定的な検査を優先する。現在のimplementが要求する契約確認で十分か比較し、手順不足が再現した場合だけ最小の更新方向を作る。
[caller-suite](../examples/caller-suite.json)は探索用。以下の架空fixtureを毎回同じ初期状態へ複製する。外部サービス・実配備・credentialは不要。

```yaml
# caller-permission-gap: caller.yaml
jobs:
  deploy:
    permissions: {contents: read}
    uses: ./.github/workflows/deploy.yaml
# deploy.yaml の契約: contents:read と actions:read を要求
```

validationはcallerに両読取権限を設定した正常系。testはA→B→Cの3ファイルにし、Aのactions:readだけを欠落させる。予算は最初にtrainの現行版とskillなしの2実行ずつ、計4実行までとする。差がなければ追記しない。候補を作る場合は別の編集予算と親snapshotを固定してからvalidationへ進む。
実際の初期ファイルは[train caller](../examples/caller-fixtures/train/.github/workflows/caller.yaml)、[validation caller](../examples/caller-fixtures/validation/.github/workflows/caller.yaml)、[test caller](../examples/caller-fixtures/test/.github/workflows/caller.yaml)から参照できる。対応するtrain/validation/testディレクトリを試行fixtureとして複製する。これらを実repoのworkflowや外部CIへ登録しない。

## 比較条件と未実施事項

[skill-workbenchの評価手順](../../skill-workbench/references/eval-loop.md)と[実験契約](../../skill-workbench/references/experiment-contract.md)を正本として使う。suiteのJSON形式を確認しても、評価実行・採点・改善実証は完了していない。suite内のtestも今回の作成担当に見えているため、独立した最終holdoutの証拠にはしない。選択後の最終確認には別文脈で新しいケースを用意する。
実行時にはmodel・推論設定・上位指示・tool・fixture・suite版と反復を固定し、診断/編集履歴を継承しない実行担当と独立した採点を使う。重要な権限退行を平均改善で相殺しない。実験結果と元事例との対応はGit外の情報scope別archiveへ保存する。
