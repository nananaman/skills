---
name: nono-sandbox-maintenance
description: nono sandbox 内で filesystem・network・command・子 process が拒否されて agent や開発ツールが失敗するときに、audit・denial report・why・profile diff から原因を特定し、最小権限の profile patch を作成・検証する。nono の初回導入、通常の agent 操作、SRT 固有の ghost artifact、拒否と無関係な CLI 障害には使わない。
---

# nono sandbox maintenance

nono の拒否を再現し、必要性を判定したうえで、最小 profile patch と回帰可能な境界検証へ固定する。
観測された access や denial-review の提案を、そのまま永続許可へ昇格させない。

## 手順

### Step 1: 最小再現と対照実験

1. profile、exact command、期待結果、error、exit status を記録する。
2. 同じ profile と最小 command で再現する。
3. sandbox 外では成功し、nono 内だけで失敗するか確認する。sandbox 外の実行が destructive、外部状態変更、credential 利用を伴う場合は実行せず、既存ログかユーザー確認を根拠にする。
4. command が途中まで成功した場合は、外部状態を読み取り確認してから再実行・cleanup を判断する。

完了条件: nono 起因である根拠、または別原因として終了する根拠が得られた。

### Step 2: denial を分類する

直近 session と解決後 profile を確認する。

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

完了条件: denial の対象、操作種別、根拠となったrule、または未特定理由が記録された。

### Step 3: 不足 capability を発見する

通常は現行 profile のまま `nono run` で再現し、終了時のdenial reportを読む。

```sh
nono run --profile <profile> -- <command> <args...>
```

対話的な denial-review では候補を保存せず終了し、Step 4で個別に判定する。
`nono learn` は0.68.0でdeprecatedなので通常 pathでは使わない。auditやdenial reportで観測できず、legacy traceが必要な場合だけ、ユーザー承認後に限定commandへ使う。

```sh
nono learn --trace --timeout <seconds> -- <command> <args...>
```

macOSで `fs_usage` などのために `sudo` が必要なら、実行前にユーザーへ確認する。
credential読取、公開操作、破壊的操作をdiscovery目的で追加実行しない。

完了条件: 不足候補が列挙された、または再現範囲では不足なしと確認された。

### Step 4: 候補を判定する

各候補を次の順で判定する。

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

完了条件: すべての候補に分類と理由が付いた。

### Step 5: source-of-truthへpatchする

ユーザーがprofile修正を明示している場合だけ、`profile` 候補をsource-of-truthへ反映する。`~/.config/nono/profiles` が展開先やsymlink先なら直接編集しない。修正が未承認ならpatch案を提示して停止する。

filesystemはdirectory全体のread-writeより、read-only、単一file、製品専用state directoryを優先する。credential実値をprofile、log、reportへ書かない。

command policyは用途ごとに三段階で設計する。

- `allow`: 観測系で外部状態を変更しないargv
- `approve`: 変更系、cleanup、pull / pushなど人間判断を残すargv
- `deny`: credential変更、host設定変更などagentへ委譲しないargv

未分類commandを `deny` と `approve` のどちらにするかは、ユーザーの運用方針と失敗時の影響で決める。常にdefault denyとは限らない。`nono why --command` で各branchを実行せず検証できる形にする。

完了条件: patchが候補と一対一に対応し、無関係な権限を含まない。

### Step 6: macOSの子processを扱う

このbranchは、親commandが内部でFoundation `Process`、shell、absolute pathなどから子processを起動して失敗した場合だけ使う。

1. 公式source、実行ログ、実機helpのいずれかで子executableとargvを確認する。
2. PATH shimで制御できる呼出しか、absolute pathのdirect execかを分ける。
3. command policyの `executable` はwrapperではなく実体をpinできるか確認する。wrapperが設定する必須environmentがあれば `environment.set_vars` で明示する。
4. `allow_direct_exec_bypass` はpinしたpolicy-controlled command本体のdirect invocation用であり、親commandが起動する任意の子executableを許可するfieldではない。子processの許可へ流用しない。
5. `unsafe_macos_seatbelt_rules` が必要なら、対象commandのchild sandbox内でexact executableだけを許可する。directory prefixや任意process execへ広げない。
6. OS tool自身がsandbox実行を拒否する場合は権限追加を止め、sandbox外の人間向け診断へ分離する。

raw Seatbelt ruleはvalidator warningを残す設計上の例外である。警告を消すためにscopeを広げない。

完了条件: child execの経路、pinした実体、追加rule、またはsandbox内で対応不能な理由が明示された。

### Step 7: 検証する

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

完了条件: validate、正常系、近接境界、diff check、残る制約が揃った。

## 出力

- 症状と最小再現
- denial分類、対象、根拠
- 候補ごとの `reject` / `temporary` / `profile` / `unknown`
- source-of-truthのprofile diff
- validate、正常系、allow / approve / deny境界
- cleanup結果
- 残るrisk、OS制約、未解決事項

patchしない場合は理由と根拠を報告する。patch案だけなら `proposed / unapplied`、検証は `not run: profile修正未承認` とする。

## 安全ルール

- denial report、denial-review、legacy learnの候補を自動適用しない。
- protected pathのdenyを動作させる目的だけで解除しない。
- profile修正、session approval、`sudo`、credential利用、外部状態変更は、それぞれユーザーの指示範囲を確認する。
- diagnostic目的で削除、prune、再install、service restartを先に行わない。
- commit、push、profile install、agent wrapper切替は明示依頼がある場合だけ行う。

## 失敗時

- auditにeventがなければdenial reportを使い、それでも観測不能なら限定したlegacy traceを検討する。
- shell、wrapper、absolute path、外部daemonを別経路として扱い、単一prefix ruleで解決したと判断しない。
- incidental denialを追加しても症状が変わらなければ撤回し、原因候補へ戻る。
- source-of-truthが不明なら編集せず、候補pathと発見根拠を示す。
