# Review Protocol

`review-diff-code`を実行するときだけ読む。

## Reviewer roster

helperの`prepare`で固定されたGit targetをleadが予備調査し、主要failure domainを所有する動的reviewerを1〜2人選ぶ。
helperが固定Adversarialを追加するため、`reviewers`へAdversarialを書かない。

```json
{
  "reviewers": [
    {
      "id": "runtime-lifecycle",
      "name": "Runtime Lifecycle",
      "expertise": "常駐serviceの状態遷移、resource ownership、障害復旧",
      "mission": "race、stale state、二重所有、cleanup漏れを発見する",
      "focus": "listener reconciliationとpublish直後のversion遷移",
      "reason": "listener管理と更新処理が変更されているため"
    }
  ],
  "adversarial": {
    "excluded_context_paths": [
      "plans/",
      "docs/design/"
    ]
  }
}
```

`expertise`は再利用可能な専門領域、`mission`は所有するfailure class、`focus`は今回優先するhotspot、`reason`は選定根拠とする。
主要failure domainが一つなら1人、独立した主要domainがあるなら2人を選ぶ。
万能roleや単一のyes/no質問は避ける。

`excluded_context_paths`にはplan、issue、Design Docなど実装意図を含むrepository-relative pathだけを指定する。
helperはAdversarialのGit commandと変更path inventoryの両方からこれらを除外し、reviewerもこれらを読まない。
これはcontext-level isolationであり、filesystem access controlではない。

## Run

1. ユーザー指定のmode / base / commitを優先する。
   dirty worktreeは`local`、単一commitは`commit`、それ以外はPRの実baseまたは`origin/main`に対する`branch`を使う。
2. helperの`prepare`を実行する。
   helperはbranchのbase/head、commit、またはlocalのHEADをfull commit IDへ固定し、変更pathとrepository stateを保存する。
3. leadは返された固定targetに対してdiff stat、changed-file inventory、必要なdiffと周辺codeを予備調査し、rosterを作る。
4. `route --roster-file`を実行する。
5. 各reviewerを`spawn_agent`の`fork_turns="none"`で並列起動する。
   実行環境がmodel overrideを提供する場合は、reviewに十分な能力を持つ安価側modelを選び、reasoning / thinkingは`high`にする。model名は固定しない。
   適合するoverrideがない場合は既定modelを使い、review自体を失敗させない。
   自分のprompt fileだけをtask inputにし、helperが安全にquoteした`git -C <fixed-repository>` commandで固定targetとrepositoryをread-onlyで調査して、指定result fileへ結果だけを書く。
   必要な外部contractは公式一次資料を参照できる。
   file変更、Git状態変更、build、lint、test、nested agent、他reviewerとの通信は禁止する。
6. `collect`を実行する。
   `partial_failure`では成功reviewerのfindingを使えるが、clean判定は禁止する。
   `failed`または`repository_drift`ではreview不能として停止する。
7. candidate findingをevidenceで検証し、accepted / rejectedを決める。
8. 成否にかかわらず`cleanup`を実行し、leadが作成したroster一時fileも削除してledgerを報告する。

```bash
helper=~/.agents/skills/review-diff-code/scripts/review-diff-code.py
"$helper" prepare --mode branch --base origin/main
"$helper" route --run-dir <run-dir> --roster-file <roster-json>
"$helper" collect --run-dir <run-dir>
"$helper" cleanup --run-dir <run-dir>
```

helper responseのpathを推測や書き換えなしで後続taskへ渡す。
helperのlifecycle errorはstderrのJSON `error.code`で判断する。

## Reviewer evidence

reviewerは最初に固定targetのdiff statとchanged-file inventoryを確認し、自分の専門性に必要なdiff、周辺code、test、型、schema、Git履歴を調査する。
変更path inventoryはcontrol characterをescapeしたJSONとして扱う。
local modeのuntracked symbolic linkは`lstat`でlink自体のpath、type、modeを、`readlink`でdestination文字列を確認できる。
link targetをdereferenceまたはopenしてはならない。
generated codeをhelperが推測で分類または除外しない。
reviewerはinventoryから生成物の存在を認知し、generator、source schema、設定、consumer、検証codeを必要な範囲で調べる。
実行による証明が必要なcandidate findingには未検証の前提を明記し、leadが採否判断時に必要なtestを実行する。
