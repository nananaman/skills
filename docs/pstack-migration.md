# pstackを標準にする移行

この差分は、Codexでpstackのnative plugin一式を標準の開発フローにし、本人管理packageを補完専用へ変える準備です。
導入版0.2.0の正本commit `d25aec07e3fd2695165e274330afa7d183ba3e6a` を基にしています。
互換確認に使ったpstack版と全件分類は [pstack.lock.json](../pstack.lock.json) に記録します。
実際のnative導入元とfull SHAの正本はdotfilesの `agent-plugins.toml` とし、手動の別管理にしません。
旧checkoutや実行中cacheを直接編集しません。

## 配布するもの

native plugin `nananaman-pstack-supplement` 0.3.0は13スキルだけを公開します。
汎用15スキルのSKILL.mdは配布treeから除き、pstackの同名tdd・標準routerとの衝突を解消します。
旧版はGit上のbaselineを使って復旧でき、配布treeへ互換copyを残しません。
Claude等の既存APM clientは、Git上の旧版24件をfull SHA参照で維持します。23件はbaseline、skill-maintenanceは既存ユーザー変更の`8f1e4a66cd5334a00f4e899b2ec8c200a2003f91`を保持します。Codex用の現行正本に削除済みの旧skillをコピーしません。
公開前にbaselineを指す復旧tagを作り、commitとの一致を検査します。
tag・commit・pushは今回の編集だけでは実行しません。

| 役割 | 移行先 |
| --- | --- |
| implement、create-plan、review-plan、design/PRD系、grilling、task-breakdown | poteto-mode、architect、pstackの計画と判断手順 |
| 既存tdd、review-diff-code | pstack:tdd、interrogate、必要時thermos |
| prototype、handoff | pstackのPrototype、Session pickup、Pause safely |
| create-pr | pstackのOpening a PRとCI手順。日本語・draft・命名の規約はchouge-gitが補う |
| chouge-writing、test-writing-style | 文体・テストの表現と公開契約を補う。別の全体進行を起動しない |
| skill-maintenance | discoveryから除去。資材はtoolsへ移し、現在の自動化は切替承認まで変更しない |
| skill-workbench | reflect由来の提案について、明示依頼された本人管理の評価・配布だけを補う |

## 設定の正本

dotfilesの `home/.agents/AGENTS.md` を一つの正本とします。
CodexのAGENTSとpstack-modelsは同じ正本へのsymlinkを使う案を準備します。
モデル行はCodexのときだけ適用し、役割とeffortを明示します。
sheet readerが未知の行を無視する性質を使い、同じ正本からroleとhook設定を読む設計です。
これは上流setupの「AGENTSへモデル行をコピーする」部分の適応であり、上流codeの改変ではありません。
通常起動・resume・compactでの読込と重複の有無はnative pilotで確認します。

全モデルが同一providerなので `panel vendors: any` を明示し、vendorの多様性を主張しません。
session effort helperは起動せず、全dispatchで明示effortを使います。
既存Orca・textlint hookは維持し、pstack SessionStartだけを別途確認して信頼します。
最終目標はhook ONですが、設定候補の作成やplugin登録を信頼操作の承認とは扱いません。

## 隔離native pilot

第三者配布元は `michael-denyer/pstack-claude`、固定版は0.9.114、commitはlockに記録します。
初回の取得はsource確認だけとし、plugin登録やscript実行と区別します。
native full pluginを使い、2スキルだけの切り出しを移行先にしません。

1. privateな新しいCODEX_HOMEとfixture用workspaceを用意する。既存のauth、sessions、state、hook信頼、plugin cacheをコピーしない。
2. 既存のAGENTSが適用される範囲、native skill一覧、CLI版、モデル一覧、初期ファイルのhashを記録する。
3. 固定commitのsource、native manifest、hook本体と読取資材を確認したうえで、操作時の承認を得て隔離marketplace/pluginへ登録する。
4. 独立したモデル認証が必要ならここで停止して接続経路を確認する。既存authのcopyやsymlinkで隔離を弱めない。
5. 明示的にpoteto-modeへ入り、小さなfeatureを計画・設計・TDD・実装・実CLI検証・interrogateへ通す。担当数、時間、token、未取得の費用を記録する。
6. draft PR段階は対象の本人管理repo・branch・公開差分を確認して行う。ローカル文案だけをPR作成成功としない。merge・deploy・ready化は行わない。
7. reflectは許可済みの現在の会話digestで明示呼出しし、提案だけを一つのprivate成果物へ保存する。Accepted編集もBacklog起票も行わない。
8. pstack hookは定義と依存を個別に承認・信頼してから、通常起動・resume・compact時のroutingを確認する。全hookの包括的な信頼は行わない。

## 受入

旧方式との勝敗を移行開始の条件にしません。
移行先での完成と境界を確認します。

- 旧implement・tdd等がskill一覧と実選択に出ず、pstack全treeと補完13件を利用できる。
- architectとinterrogateの担当が実装者と会話を分離し、指摘の再現出力を主担当が確認する。
- 日本語、命名、draft PR、必要な契約コメントと検証、許可workspaceを守る。
- 最終編集後にtestと実CLIの期待出力が一致し、未実施を成功として報告しない。
- 指定した有効モデルと明示effortを使い、容量・時間・環境障害を品質不合格や成功と混ぜない。
- reflectが履歴探索や無承認のskill・AGENTS・tracker変更を行わない。
- 軽微な変更と別タスクでも再現し、resume・compactでroutingが変わらない。

## 切替と復旧

native pilotの受入後、一つの普段のrepoを選び、scoped切替承認を得て進めます。
旧generic pluginを無効化し、補完pluginとpstackを有効化します。
APMの自己skill参照は他client用の旧版viewとして固定し、targetsはclaude/codex/agent-skillsを維持します。現行sourceへのlink切れを防ぐため、互換manifestの反映とAPM同期を、本人source0.3.0への切替より先に行います。Codexだけはdotfilesの`agent-routing-apply`で旧native pluginと旧loose skill24件を無効化します。新pluginのsource/version/cacheが両方とも検証済みでなければ、その適用は停止します。同時にmulti_agentとagentsを有効にし、同時担当数を2に制限します。変更するruntime keyの元値もreceiptから復旧できます。新しい機械でも、APM install後にこの明示操作を行うことで旧入口の再露出を防ぎます。
Claude/Pi等は従来のimplementとskill-workbenchの入口を維持し、pstack移行をこのCodex切替から推測しません。互換APM viewの更新は、各clientの移行を依頼するまで固定されます。
既存dotfilesの未コミットAPM・mise変更は保持し、切替準備で上書きしません。
既存の日次自動化を止める・目的変更する操作は、切替時に別途承認を得ます。

旧plugin登録、対象AGENTSのlink先、pstack専用のhook状態、Codex discoveryの変更分だけを復旧します。routing taskは適用前の対象値だけをprivate receiptへ保存し、rollback時は無関係な後続編集を保ちます。対象値自体が並行変更されていれば停止します。sourceとplugin/linkの復旧はそれぞれのowner手順で行い、routing rollbackだけを全移行の復旧とは扱いません。
Orca・textlint・無関係の設定を一括上書きしません。
拒否済み履歴の取得、誤った外部操作、検証欠落があれば該当工程の展開を止め、原因を修正します。
復旧tagと実導入baselineの一致、復旧後のskill一覧とroutingを確認して完了します。
