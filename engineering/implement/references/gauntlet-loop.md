# Gauntlet Loop

`implement`の通常execution strategy。
goalとquality barを固定し、artifactを変更するBuilderとfresh Criticを分離して、最大のaccepted gapから収束させる。

## Loop

1. lead agentがgoal、quality bar、authority boundaryを確認する。
2. artifactと検証基準のownershipに沿って、独立して改善可能なunitへ分ける。
3. unitごとにBuilderを割り当て、artifactを変更させる。
4. fresh Criticへactual artifactと、そのunitに必要なquality barだけを渡す。
   Builder reasoning、自己評価、過去iterationの説明は渡さない。
5. 比較対象がある場合、current outputとreference artifactをblindに比較させる。
   どちらがquality barを満たすか、最大のgap、actionableな改善だけを返させる。
6. lead agentがcandidate findingをevidenceでaccepted / rejectedに分ける。
7. accepted findingのうち、quality barへの影響が最大のgapをBuilderへ戻す。
8. actual artifactを再生成・再実行し、fresh Criticで評価する。
9. `implement`のterminal outcomeに達するまで繰り返す。

複数unitを別々に改善したことで一貫性が崩れるriskがある場合、major iteration後にsmoothing Builderとfresh Criticを追加できる。
smoothingはintegration、cohesion、重複、表現の一貫性を整え、architectureを無条件に再設計しない。

## Quality comparison

reference artifactはquality barの一部であり、完全な仕様とは扱わない。
「referenceを超えた」という主観だけで完了せず、必須assertionと残るactionable gapを確認する。

Criticにはsummaryではなくinspect可能なoutputを渡す。

- running application、interaction、screenshot。
- test result、benchmark、generated output。
- rendered document、export artifact。
- code diff、type / schema / API contract。

比較不能または不足するevidenceを推測で補わない。
lead agentへ不足artifactと、その不足が阻む判断を返す。

## Progress

各iterationで次を更新する。

- active unitとBuilder / Critic。
- inspected artifact。
- accepted / rejected / fixed。
- largest remaining gap。
- quality barの充足状態。
- terminal outcomeへ進めないblocker。
