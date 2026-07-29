# Review Protocol

`review-diff-code`を実行するときだけ読む。

## Reviewer roster

Context Builderの`risk_surfaces`を採用、統合、棄却し、変更リスクに応じた動的reviewerを1〜2人選ぶ。
動的reviewerだけをJSON arrayとして一時fileへ書く。
helperが固定Adversarialを自動追加するため、rosterへAdversarialを書かない。

```json
[
  {
    "id": "runtime-lifecycle",
    "name": "Runtime Lifecycle",
    "expertise": "常駐serviceの起動・停止、並行状態遷移、resource ownership、障害からの復旧",
    "mission": "差分が導入するrace、stale state、二重所有、cleanup漏れ、再起動時の不整合を発見する",
    "focus": "listenerのreconciliationとpublish直後のversion遷移",
    "reason": "常駐serverのlistener管理と更新処理が変更されているため",
    "context_mode": "impact"
  }
]
```

`impact`はimplementation diff、変更されたcontext document、related filesを受け取る。
`implementation`はimplementation diffだけを受け取る。
`risk_surfaces`はroster選定専用であり、どちらのcontextにも含めない。
動的reviewerには通常`impact`を使う。helperが追加するAdversarialは固定promptと`implementation`を使い、leadが可変fieldを与えない。

`expertise`は複数の変更で再利用できる専門領域、`mission`はその専門家が所有するfailure class、`focus`は今回優先して調べるhotspot、`reason`は選定根拠とする。
`focus`は優先事項であり、`expertise`と`mission`に属する探索を限定しない。
主要failure domainが一つなら1人、独立した主要domainまたは異なる種類の専門性が必要なら2人を選ぶ。

### 専門家の粒度

次は固定catalogではなく、適切な専門性の粒度を示す例である。
差分に合えば例にない専門家も定義してよい。

- `境界互換性`: API、型、schema、CLI、設定、consumerとの境界を専門とし、後方互換性や入出力contractの不整合を所有する。
- `Runtime Lifecycle`: 起動・停止、並行処理、resource ownership、recoveryを専門とし、race、stale state、cleanup漏れを所有する。
- `データ整合性`: serialization、永続化、migration、transactionを専門とし、データ破壊、欠落、重複、部分更新を所有する。
- `Security Boundary`: trust boundary、認証・認可、入力処理、secretを専門とし、権限逸脱、境界迂回、情報漏洩を所有する。
- `検証信頼性`: test oracle、fixture、mock、異常系を専門とし、退行を検出できないtestや実環境との乖離を所有する。
- `構造設計`: ownership、layering、依存方向、変更の局所性を専門とし、責務の誤配置、hidden coupling、変更増幅を所有する。
- `インタラクションUX`: ユーザーの目的、操作flow、状態feedback、error recovery、認知負荷を専門とし、完了不能なflow、誤操作、回復手段の欠落を所有する。
- `Visual Interface`: 情報階層、layout、spacing、typography、responsive behavior、視覚的一貫性を専門とし、sourceから根拠を示せる表示上の退行を所有する。
- `Accessibility`: keyboard操作、focus、semantic structure、contrast、支援技術との互換性を専門とし、利用不能または理解不能になるregressionを所有する。
- `Content Design`: label、説明、error message、用語、次の行動の明確さを専門とし、誤解、判断不能、不整合な案内を所有する。

UI/UX系reviewerも、source diff、context file、related filesから確認できる事実だけを根拠にする。
render結果を受け取っていない場合に、見たかのようなvisual findingを報告させない。

たとえばインタラクションUXは次のように定義する。

```json
{
  "id": "interaction-ux",
  "name": "インタラクションUX",
  "expertise": "ユーザーの目的に沿った操作flow、状態feedback、error recovery、認知負荷",
  "mission": "完了不能なflow、状態の分かりにくさ、誤操作を誘発するinteraction、回復手段の欠落を発見する",
  "focus": "更新待機中、更新成功、接続断の各状態が利用者へどう伝わるか",
  "reason": "自動更新される画面の状態遷移と利用者feedbackが変更されているため",
  "context_mode": "impact"
}
```

`Correctness`、`Code Quality`、専門性が「コード全般」のような万能roleは避ける。
missionが「問題がないか確認する」だけではfinding ownershipがない。
また、`ETag比較が正しいか`のような単一のyes/no質問を専門性にしない。
この場合はconditional request、validator、表示中version、競合状態を所有する`HTTP Cache and Versioning`を専門家とし、ETag比較を`focus`へ置く。
複数reviewerの専門領域と所有するfailure classが実質的に重複する場合は、統合するか境界を引き直す。

## Run

1. ユーザー指定のmode / base / commitを優先する。
   dirty worktreeは`local`、単一commitは`commit`、それ以外はPRの実baseまたは`origin/main`に対する`branch`を使う。
2. helperの`prepare`を実行する。
   返されたprompt fileだけをtask inputとしてContext Builderをfresh subagentで起動し、指定されたresult fileへJSONだけを書かせる。
3. 各attempt前に`reset-context`、終了後に`validate-context`を実行する。
   `context_result_invalid`またはsubagent failureはfresh subagentで1回だけ再試行する。
   `repository_drift`はrunを破棄し、現在の累積diffから`prepare`をやり直す。
4. rosterを作り、`route --roster-file`を実行する。
5. 各reviewerを`spawn_agent`の`fork_turns="none"`で並列起動する。
   自分のprompt fileだけを読み、指定されたresult fileへ結果だけを書かせる。
   repositoryの追加調査やtool利用をtaskに含めない。
6. `collect`を実行する。
   `partial_failure`では成功reviewerのfindingを使えるが、clean判定は禁止する。
   `failed`または`repository_drift`ではreview不能として停止する。
7. candidate findingの重複をissue単位に束ね、evidenceでaccepted / rejectedを決める。
8. 成否にかかわらず`cleanup`を実行し、自分で作成したroster一時fileも削除して、ledgerを報告する。

```bash
helper=~/.agents/skills/review-diff-code/scripts/review-diff-code.py
"$helper" prepare --mode branch --base origin/main
"$helper" reset-context --run-dir <run-dir>
"$helper" validate-context --run-dir <run-dir>
"$helper" route --run-dir <run-dir> --roster-file <roster-json>
"$helper" collect --run-dir <run-dir>
"$helper" cleanup --run-dir <run-dir>
```

helper responseのpathを推測や書き換えなしで後続taskへ渡す。
helperのlifecycle errorはstderrのJSON `error.code`で判断する。
