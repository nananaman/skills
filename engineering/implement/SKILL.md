---
name: implement
description: 明示されたgoalをinspectableなquality barを満たす成果物として実装し、独立したBuilderとCriticのfeedback loopをlead agentが編成・収束させるときにユーザーが明示的に使う。通常の単発実装、自動発火、plan作成だけ、reviewだけ、prototypeだけでは使わない。
disable-model-invocation: true
---

# Implement

goalとquality barに対して、lead agentが設計、分解、実装、独立評価、収束を管理する。
特定のarchitectureや逐次編集手順は固定しない。

## Contract

実装前に次を一意にする。

- user-visible goalとscope。
- 自律実行できるactionと、追加確認が必要なauthority boundary。
- actual artifactに対して判定できるquality bar。
- completionと、停止時に残件として返す条件。

quality barには、利用可能な範囲で高忠実度なevidenceを使う。

1. acceptance test、benchmark、schema、type、API contract。
2. 比較可能なreference artifact。
3. 既存behaviorと明示された変更要求。
4. 観測可能なacceptance criteria。

`production ready`や`よくする`のように判定不能な表現だけで開始しない。
安全な調査後もquality barを作れない場合は、最小の不足artifactまたはuser判断を求めて停止する。

## Orchestration

lead agentはgoalとquality barを維持したまま、architecture、task decomposition、execution strategy、Builder / Critic編成を選ぶ。
単位は、独立した成果物または検証基準を持ち、同時編集競合を起こしにくい範囲にする。
分割自体を目的にしない。

Builderはartifactを作成または変更する。
同じ変更を行ったBuilderを、その変更の唯一の評価者にしない。

Criticはfresh contextでactual artifactと必要なquality barを評価する。
Builderのreasoning、自己評価、作業履歴をCriticへ渡さない。
codeはdiffと実際のcontract、UIはrunning applicationやscreenshot、文書はrendered artifact、性能はbenchmarkのように、要約ではなく成果物をinspectさせる。
fresh contextを用意できない場合はBuilderの自己評価で代替せず、未実施のquality gateと残るriskを報告して停止する。

Criticの出力はcandidate findingである。
lead agentがactual artifactとquality barで検証し、重複を束ね、accepted / rejectedと理由を決める。
Criticの多数決や自己申告をquality gateにしない。

通常は[`references/gauntlet-loop.md`](./references/gauntlet-loop.md)をexecution strategyとして使う。
同じcontractをより確実に満たせる方法がある場合、lead agentは別strategyを選べる。
その場合は選定理由をprogress reportへ残す。

実行codeのbehaviorを変更するBuilderは`tdd`、テストを追加・変更する場合は`test-writing-style`を使う。
code diffの独立評価には`review-diff-code`を使えるが、すべてのartifact評価をcode reviewへ寄せない。

## Progress

利用者が作業を中断せず、現在地と残件を確認できる形を維持する。

- 短い作業: 会話上のstatusと最終ledger。
- 複数unitまたは複数iteration: Markdownのprogress artifact。
- 視覚比較がquality barに含まれる: screenshot、preview、必要ならHTML。

progressにはgoal、quality bar、unit、Builder / Critic、current status、accepted / rejected / fixed、残るlargest gapを含める。
progress artifact自体を成果物にせず、作業規模に比例させる。

progress を自己完結した単一 HTML として作った場合は、`host-artifact publish <html-file> --name <artifact-name>` で配信する。
material iteration ごとに同じ workspace と artifact name で再 publish し、安定した URL を維持する。
HTML の live reload は `host-artifact` が配信用 copy へ付与するため、progress生成側で polling script を持たない。

## Completion

次のいずれかで終了する。

- quality barの必須assertionを満たし、actionable gapが残っていない。
- 次の改善がscope、risk、costを不釣り合いに増やす。
- 同じfindingが再発し、現在の方針では収束しない。
- quality bar同士が矛盾する。
- user判断、追加authority、不足artifactが必要。
- userが停止した。

固定iteration数では終了させない。
完了時はactual artifactに対する検証結果を報告する。
停止時は理由、満たしたquality bar、未解決gap、次に必要な最小actionを報告する。
