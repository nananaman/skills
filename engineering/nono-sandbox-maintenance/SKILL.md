---
name: nono-sandbox-maintenance
description: nono sandboxのアクセス拒否を診断し、必要最小限のprofile修正と検証を行う。拒否と無関係なCLI障害には使わない。
---

# nono sandbox maintenance

nono の拒否を再現し、必要性を判定したうえで、最小 profile patch と回帰可能な境界検証へ固定する。
観測された access や denial-review の提案を、そのまま永続許可へ昇格させない。

## 手順

### 1. 最小再現と対照実験

1. profile、exact command、期待結果、error、exit status を記録する。
2. 同じ profile と最小 command で再現する。
3. sandbox 外では成功し、nono 内だけで失敗するか確認する。sandbox 外の実行が destructive、外部状態変更、credential 利用を伴う場合は実行せず、既存ログかユーザー確認を根拠にする。
4. command が途中まで成功した場合は、外部状態を読み取り確認してから再実行・cleanup を判断する。

### 2. 拒否を分類する

直近 session と再現に使用した profile を確認する。

```sh
nono audit list
nono audit show <session-id> --json
nono profile show <profile> --json
```

次のいずれかへ分類する。

- filesystem read / write / execute
- network host / port
- command argv policy
- child process / absolute executable
- credential / protected path
- macOS Seatbelt operation
- nono 以外の失敗

policyだけで判定できる対象は実行せず `nono why` を使う。

```sh
nono why --profile <profile> --path <path> --op <read|write|readwrite>
nono why --profile <profile> --host <host> --port <port>
nono why --profile <profile> --command <command> -- <args...>
```

### 3. 不足する権限を見つける

通常は現行 profile のまま `nono run` で再現し、終了時のdenial reportを読む。

```sh
nono run --profile <profile> -- <command> <args...>
```

対話的な denial-review では候補を保存せず終了し、Step 4で個別に判定する。
auditやdenial reportで観測できずlegacy traceが必要な場合だけ、[限定traceの手順](references/legacy-trace.md)を読む。

### 4. 候補を判定する

各候補について次の必要性と境界を判断する。

1. 依頼された正常系に必要か。
2. より狭いpath、access mode、host、exact executable、argv ruleで表現できるか。
3. secret、keychain、browser data、shell history、他agentの永続領域に触れないか。
4. 外部daemon・service・子processを介して権限が拡張しないか。
5. 一回限りならprofileではなくsession approvalで扱えるか。
6. denialが成功に無関係なtelemetry、logging、locale、preference readなら追加せずに済むか。

分類:

- `reject`: 不要、危険、または原因と無関係
- `temporary`: 一回限りのapproval
- `profile`: 反復利用する最小権限
- `unknown`: 根拠不足。永続変更しない

### 5. source of truth を修正する

依頼・会話内の許可が対象profileと必要な権限変更を含む場合は、`profile` 候補を正本へ反映し、検証まで進める。「直して」が権限拡大の一括許可とは限らない。追加する権限が許可範囲外なら具体的なpatch案を示し、その反映だけを保留する。
`~/.config/nono/profiles` が展開先やsymlink先なら正本を編集する。

filesystemはdirectory全体のread-writeより、read-only、単一file、製品専用state directoryを優先する。credential実値をprofile、log、reportへ書かない。

command policyは用途ごとに三段階で設計する。

- `allow`: 観測系で外部状態を変更しないargv
- `approve`: 変更系、cleanup、pull / pushなど人間判断を残すargv
- `deny`: credential変更、host設定変更などagentへ委譲しないargv

CLIがcredential fileを必要とする場合は、親sessionへfileやtokenを開示する前に、そのCLIだけをTool Sandboxへ分離できるか確認する。
credentialをstdoutへ出す限定subcommandがあるなら、親networkのTLS interceptionやcredential proxyを設計する前に、per-intercept sandboxと`capture_credential`で実値をbroker内へ閉じ込められるか検証する。
通常操作用sandboxとcredential取得用sandboxのfilesystem、network、environmentを別々に定義し、親sessionからprotected pathのdenyを外さない。

未分類commandを `deny` と `approve` のどちらにするかは、ユーザーの運用方針と失敗時の影響で決める。常にdefault denyとは限らない。`nono why --command` で各branchを実行せず検証できる形にする。

### 6. 子プロセス固有の失敗

macOSで親commandが子processを起動して失敗する場合だけ、[子プロセスの診断](references/child-processes.md)を使う。

### 7. 検証する

最初に`NONO_CAP_FILE`の有無を確認する。
macOSで値が設定済みなら二重の`nono run`をruntime testとして起動しない。
さらに対象commandの解決先が`$NONO_TOOL_SANDBOX_SHIM_DIR`配下で実行可能な場合だけ、現在のsessionへ注入されたTool Sandbox shimで正常系を確認する。
credential非露出はstdoutを変数へ捕捉して期待するnonceの形式だけを判定し、成功時も失敗時も捕捉値をterminal、log、reportへ表示しない。
新規sessionの起動を必要とする独立runtime testはsandbox外で実行し、内側profileの不具合と外側sandboxによる拒否を分けて報告する。

```sh
nono profile validate --strict <profile-file>
nono profile show <profile> --json
nono profile diff <base-profile> <profile>
```

1. 継承先profileもすべてvalidateする。
2. Step 1の正常系を再実行する。
3. `nono why` で近接するallow / approve / denyを各1件以上確認する。外部状態を変える拒否テストは実行しない。
4. commandが外部状態を変更した場合は、読み取り系commandで結果を確認し、自分が作成した一意resourceだけをcleanupする。
5. `git diff --check` と対象diffを確認する。

CLI versionとprofile schemaが合わない、またはhelpにないfieldを使う必要がある場合は、`nono profile schema` と実機versionを確認し、validationが通るまで永続変更を完了扱いしない。

## 報告

原因と根拠、採用した最小権限、正本の差分、実施した検証と未解決事項を報告する。
外部状態を変えた場合は結果とcleanupも示す。patch案だけの場合は未適用と明記し、未実施の検証を成功扱いにしない。

## 安全ルール

- denial report、denial-review、legacy learnの候補を自動適用しない。
- protected pathのdenyを動作させる目的だけで解除しない。
- profile修正、session approval、`sudo`、credential利用、外部状態変更は、それぞれユーザーの指示範囲を確認する。
- diagnostic目的で削除、prune、再install、service restartを先に行わない。
- commit、push、profile install、agent wrapper切替は明示依頼がある場合だけ行う。

## 失敗時

- auditにeventがなければdenial reportを使い、それでも観測不能なら限定したlegacy traceを検討する。
- audit ledgerがparse不能なら [限定した修復条件](references/audit-repair.md) を確認する。
- shell、wrapper、absolute path、外部daemonを別経路として扱い、単一prefix ruleで解決したと判断しない。
- incidental denialを追加しても症状が変わらなければ撤回し、原因候補へ戻る。
- source-of-truthが不明なら編集せず、候補pathと発見根拠を示す。
