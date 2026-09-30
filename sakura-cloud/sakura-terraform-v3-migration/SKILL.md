---
name: sakura-terraform-v3-migration
description: さくらのクラウド Terraform Provider v2(sacloud/sakuracloud) から v3(sacloud/sakura) へ移行するときに使う。sakuracloud_* 利用箇所の棚卸し、v3 未対応リソース確認、provider/resource/data source 名変更、filter 廃止、Block から Attribute への変更、State/import 移行計画、terraform plan 検証を行う。さくらと無関係な Terraform 相談、Terraform Provider 一般の作成、記事要約だけの依頼では使わない。
---

さくらのクラウド Terraform Provider v2 から v3 への移行を、既存リソースと State を壊さないよう段階的に進める。

## 基本方針

- v2 と v3 は別 Provider であり完全互換ではない。
- 既存 State は自動的に v3 リソースへ変換されない。State 移行方針を決めるまで `terraform apply` しない。
- 本番環境では、検証環境または影響の小さいリソースで import / plan 手順を確認してから進める。
- `terraform plan` で destroy / replace / recreate が出たら、意図したものかユーザーに確認する。
- `terraform apply`、`terraform destroy`、`terraform import`、State を変更する `terraform state` 系コマンドは、ユーザーの明示許可なしに実行しない。
- `terraform state show` は secret を出力し得る。AppRun env や credential を含む resource では、全量出力を CI log / 共有 terminal / agent tool transcript に残さない。agent 上では secret を含み得る resource の全量 `state show` を実行せず、ユーザー許可の上で stdout に secret が出ない抽出コマンドだけを使う。
- 一時的な migration guard を通常の Terraform graph に恒久投入しない。必要な安全策は migration runbook、import block、plan review、または明示的なユーザー確認に置く。

## 参照情報

必要になった時点で読む。

- `references/sources.md`: 公式・準公式情報源、サポート期限、Provider 名、Terraform 要件。
- `references/migration-notes.md`: v2→v3 の主な rename、構文変更、未対応リソース、リソース別注意点。

## Workflow

### 1. 対象 Terraform 構成を特定する

Terraform ファイルと State 管理方式を確認する。

```bash
find . \( -name '*.tf' -o -name '*.tfvars' -o -name '.terraform.lock.hcl' \) -print
```

確認するもの:

- `required_providers` の `sacloud/sakuracloud` / `sacloud/sakura`
- `provider "sakuracloud"` / `provider "sakura"`
- backend 設定と workspace
- module 構成
- `.terraform.lock.hcl` の Provider lock
- v3 Provider の version pin 方針。`3.1.0` など初期 v3 に固定せず、移行対象 resource が実装済みの最新 v3 patch を確認してから exact pin または lock file commit で固定する。`.terraform.lock.hcl` が `.gitignore` 対象なら lock file commit には頼れないため exact pin を使う。

### 2. v2 利用箇所を棚卸しする

まず grep / ripgrep で v2 の痕跡を一覧化する。

```bash
rg -n 'sacloud/sakuracloud|provider\s+"sakuracloud"|sakuracloud_|filter\s*\{|switch_id|weekdays|disabled\s*=|dynamic\s+"' --glob '*.tf' --glob '*.tfvars' .
```

`rg` wrapper や環境設定で `--glob` が使えない場合は、次の fallback を使う。

```bash
find . \( -name '*.tf' -o -name '*.tfvars' \) -print0 \
  | xargs -0 grep -En 'sacloud/sakuracloud|provider[[:space:]]+"sakuracloud"|sakuracloud_|filter[[:space:]]*\{|switch_id|weekdays|disabled[[:space:]]*=|dynamic[[:space:]]+"'
```

出力では次を分ける。

- Provider 設定
- resource / data source アドレス
- data source の `filter` block
- `switch_id` / `weekdays` / `disabled` など既知の属性変更候補
- Block→Attribute 変換が必要そうな nested block
- `dynamic` block を使った nested block 生成。v3 の Attribute 構文では for expression などへの書き換えが必要になりやすい。

### 3. v3 対応状況を分類する

`references/migration-notes.md` を読み、利用中の resource / data source を分類する。
ただし `未対応` は references の一覧だけで確定しない。選択候補の最新 v3 patch の Registry docs、CHANGES、または schema で未実装を確認できた場合だけ `未対応` とする。未確認なら `要調査` に留める。

分類:

- `対応済み`: selected v3 Provider に resource / data source があり、移行可能。
- `未対応`: selected 最新 v3 Provider でも未移植。v2 併用、Terraform 管理外化、または移行延期を検討。
- `要調査`: provider docs / CHANGES.md / schema を確認する必要がある。

未対応リソースを含む場合は、一括移行を前提にしない。

### 4. 移行方針を決める

各リソースについて、以下のいずれかを選ぶ。

- v3 resource 定義を作り、既存実リソースを import する。
- v3 resource として再作成する。
- v3 未対応またはリスクが高いため、当面 v2 管理を継続する。
- Terraform 管理対象から外し、コントロールパネル / API などで管理する。

State に関わる判断は、ユーザーに確認してから実行する。

### 5. `.tf` を v3 形式へ変更する

代表的な変更:

- `sacloud/sakuracloud` → `sacloud/sakura`
- Provider local name `sakuracloud` → `sakura`
- `sakuracloud_` prefix → `sakura_` prefix
- Provider version は `~> 3` だけで済ませず、移行対象 resource が実装済みの最新 v3 patch を選び、patch version pin または lock file の扱いを明確にする。初期 v3 で resource が未実装でも、最新 v3 で対応済みの可能性がある。lock file が ignore されている repository では、Provider block の exact version pin を固定方針として明示する。
  - 最新 v3 patch は推測しない。一時的に `version = "~> 3"` と fresh `TF_DATA_DIR` で `terraform init -backend=false -upgrade` を実行し、選択された version を init output または `.terraform.lock.hcl` から確認してから exact pin する。この確認は `.terraform.lock.hcl` を作業ツリーに作成・更新し得るため、実行前にユーザー許可を得るか一時コピーで実行する。実行後は lock file 差分を採用するか破棄するかを明示する。Registry 表示と GitHub release が食い違う場合は、現在の constraint で Terraform が選択した version を採用候補とし、差異を報告する。実行できない場合は Registry / release 情報で確認し、根拠を報告する。
- Terraform `output` 名、module input 名、tfvars 変数名は外部 contract として扱う。Provider/resource prefix に合わせて機械的に rename せず、互換性を保つため原則名前を維持し、value / 内部参照だけを更新する。破壊的 rename が必要ならユーザーに確認する。残存 grep では provider/resource address と public contract 名を分けて判定する。
- 既知 rename を反映する。
  - `switch` → `vswitch`
  - `vpc_router` → `vpn_router`
  - `proxylb` → `enhanced_lb`
  - `note` → `script`
  - `load_balancer` → `dsr_lb`
  - `apprun_application` → `apprun_shared`
- data source の `filter` block を通常属性へ変換する。
- nested block を Attribute 構文へ変換する。
- nested `dynamic` block は、Attribute の list / set / object を作る `for` expression へ変換する。
- `switch_id` → `vswitch_id`、`weekdays` → `days_of_week` などの属性変更を反映する。
- selected Provider version の schema を `terraform validate` と必要に応じて `terraform providers schema -json` で確認する。docs や migration note の記述を schema より優先しない。
  - backend 初期化を避ける schema 確認では、必要に応じて一時 `TF_DATA_DIR` を使って `terraform init -backend=false` → 同じ `TF_DATA_DIR` で `terraform providers schema -json` を実行する。
  - それでも backend 初期化を要求される場合、schema 確認のためだけに real backend を init しない。fallback 順は `terraform validate` の error → Terraform Registry docs → Provider source / CHANGES。schema 未取得は失敗ではなく、fallback で確認した根拠と未確認点を報告する。
- write-only (`*_wo`) field が schema にある場合は、対応する version field と運用変数を用意する。値が更新されても version が変わらなければ再送されない。
- `sakura_apprun_shared` の registry credential は、schema が対応していれば `password` ではなく `password_wo` / `password_wo_version` を優先する。schema が未対応なら Provider version を上げられないか先に確認する。
- `sakura_container_registry.access_level` は deprecated。最新 v3 schema で任意属性なら、public access 要件がない限り v2 の `readwrite` を `none` に置換するのではなく属性自体を削除する。古い v3 で required なら、まず Provider version の更新で解消できないか確認する。

詳細は `references/migration-notes.md` を確認する。

### 6. State / import 計画を作る

既存 v2 State を v3 へそのまま自動変換できる前提にしない。

import block を使う場合の基本形:

```hcl
import {
  to = sakura_server.example
  id = "<existing-resource-id>"
}
```

設定生成を試す場合:

```bash
terraform plan -generate-config-out=generated_resources.tf
```

注意:

- `-generate-config-out` は Terraform の experimental 機能として扱う。
- 既存ファイルへの出力はできない。
- 生成 HCL はそのまま採用せず、不要属性・競合属性・module 構成・変数参照へ整理する。
- `terraform import` だけで終わらせない。同じ実 resource を v2/v3 の二重管理にしないため、import 後に旧 v2 State address をどう外すか（例: `terraform state rm`）まで runbook に書く。
- import ID の形式は推測しない。Provider docs、schema、既存 State、API / control panel で確認する手順を書く。確定できない場合は `<...>` placeholder と「要確認」を明記し、確定コマンドとして提示しない。
- ID 確認に `terraform state show` を使う場合は、secret を含む resource の全量出力をログに残さない。agent 上では全量 `state show` を実行せず、ユーザー許可の上で stdout に secret が出ない ID 抽出コマンドだけを使う。

### 7. 検証する

ユーザーの許可がある範囲で実行する。

```bash
terraform fmt -check -recursive
terraform init
terraform validate
terraform plan
```

backend や実 State に触れず構文だけ確認する場合は `terraform init -backend=false` を使う。
`terraform init -upgrade` は通常検証では使わない。Provider version 選定のために最新 v3 patch を確認する場合は、ユーザー許可後に、作業ツリー差分を事前確認したうえで fresh `TF_DATA_DIR` と `-backend=false` で一時的に実行する。作業ツリーの `.terraform.lock.hcl` を変更したくない場合は一時コピーで実行する。選択された version を exact pin してから通常検証に戻り、`.terraform.lock.hcl` の差分を採用するか破棄するか、`.gitignore` 上の扱い、選択された Provider version を報告する。
`terraform validate` で resource 未対応・required/deprecated 属性・write-only field 名の不一致が出た場合は、まず selected Provider version と schema を確認する。初期 v3 の制約だけで v3 未対応と結論づけない。

plan では特に次を見る。

- 意図しない `destroy` / `replace` がないか
- import 予定リソースが `import` として扱われているか
- v2 Provider 由来の参照が残っていないか
- write-only 化した secret/password 系の差分が想定通りか
- 未対応リソースを含む module が誤って v3 化されていないか

### 8. 報告する

作業後は以下を報告する。

- v2 利用箇所一覧
- v3 対応状況の分類
- 実施した変更
- 選択した v3 Provider version と patch pin / `.terraform.lock.hcl` / `.gitignore` の扱い
- State / import 方針
- 実行した Terraform コマンドと結果
- plan 上の差分要約
- 本番適用前にユーザー判断が必要な項目

## Done Criteria

- `sacloud/sakuracloud` / `sakuracloud_*` の残存理由が説明できる。
- v3 未対応リソースの有無と扱いが明確になっている。
- 選択した v3 Provider version と固定方針（patch pin または `.terraform.lock.hcl`）が説明できる。`.terraform.lock.hcl` が ignore される場合は、その代替として exact pin する方針が説明できる。
- State 移行方針が resource 単位で説明できる。
- `terraform validate` または実行不能な理由が報告されている。
- `terraform plan` の destroy / replace / import が意図したものか確認済み、または未確認事項として明示されている。
