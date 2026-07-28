# Review Protocol

`review-diff-code`を実行するときだけ読む。

## Reviewer roster

Adversarialと、変更リスクに応じた追加reviewerをJSON arrayとして一時fileへ書く。

```json
[
  {
    "id": "contract-compatibility",
    "name": "Contract Compatibility",
    "question": "公開contractを壊す変更があるか",
    "reason": "公開APIの変更を含むため",
    "context_mode": "impact"
  },
  {
    "id": "adversarial",
    "name": "Adversarial",
    "question": "変更が安全だという主張を反証できるか",
    "reason": "必須のblind review",
    "context_mode": "implementation"
  }
]
```

`impact`はimplementation diff、変更されたcontext document、related filesを受け取る。
`implementation`はimplementation diffだけを受け取る。
Adversarialの`id`、`question`、`context_mode`は例の値から変更しない。

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
