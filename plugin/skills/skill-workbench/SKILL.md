---
name: skill-workbench
description: 明示的に依頼された本人管理skill・補完規約の評価、候補保存、差分監査、配布前検査を行う。学びの自動収集や汎用開発フローは扱わない。
disable-model-invocation: true
---

# 本人管理の補完規約を評価する

学びの入口は明示呼出しの pstack `reflect` とする。
このskillは、渡された提案や依頼済みの変更について、候補保存・比較・監査・配布前確認を補う。
履歴を探索せず、既存の日次処理を起動・変更しない。
第三者pstack本体やplugin cacheは編集しない。

## 受け取るもの

対象の正本、今回許可された操作、提案の根拠、維持する契約、未確認事項を確かめる。
reflectのAcceptedやBacklogという分類は編集・起票・公開の許可ではない。
本人管理の変更以外は、上流更新・明示fork・補完規約のどこが担当するかを先に分ける。

## 評価と監査

- 差分または一覧の監査は[レビュー手順](references/review-protocol.md)と[監査手順](references/audit-protocol.md)で行う。
- 改善効果を確かめる依頼では[評価手順](references/eval-loop.md)を読み、成果で判断できる課題と比較条件を固定する。
- 候補保存・採点・比較には[既存CLI](references/experiment-contract.md)を使う。新しい比較器は増やさない。
- 同じモデル・effort・tools・上位指示・fixture・評価版で比較する。既設pluginやAPM配置からの混入も確認する。
- 採点と初見の起動確認では、変更担当の会話を継承しない独立した文脈を使う。
- 重要な契約や権限境界の退行は平均改善で相殺しない。同点や未測定を改善へ変えない。
- pstack中心への移行は承認済みの方針とする。旧方式より優れているという比較結果を移行開始の条件へ追加しない。

評価器の変更、再現不足、実行不能は、効果の検証と分けて記録する。
既存の[合成課題](examples/practice/README.md)は目的に合う場合だけ再利用し、公開課題を秘密holdoutとして扱わない。
新規・大幅な変更のDiscoveryとRuntimeは、静的検査の成功で代替しない。

## 配布前の確認

許可された正本差分だけをpstackのauthoring・レビュー手順へ戻す。
frontmatter、inventory、リンク、公開内容、依存の版とライセンスを確かめる。
非公開の履歴、state、評価結果、認証情報はGit外へ保持する。
commit、push、draft PR、merge、install、hookの信頼は、それぞれ今回許可された範囲だけ行う。
結果は変更・検査・未検証・未実施を分けて返す。
