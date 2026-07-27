# v2 から v3 への移行メモ

このファイルは `terraform-provider-sakura` の `CHANGES.md`、README、さくらのナレッジ記事をもとにした作業用メモ。
最新の正確な schema は Terraform Registry と対象 Provider version の docs を確認する。

## 大枠の変更

- v2 は `sacloud/sakuracloud`、v3 は `sacloud/sakura`。
- Provider local name は通常 `sakuracloud` から `sakura` へ変更する。
- `sakuracloud_` prefix は `sakura_` prefix へ変更する。
- v3 は Terraform Plugin Framework ベースで、SDK v2 互換レイヤーなしの完全移行。
- v2 と v3 は完全互換ではない。
- v2 と v3 は別 Provider なので、同一構成内で併用は可能。ただし State 移行は自動ではない。
- v3 Provider は、移行対象 resource が実装済みの最新 v3 patch を確認してから patch version pin または `.terraform.lock.hcl` の commit で固定する。初期 v3 (`3.1.0` など) の schema だけで未対応と判断しない。

## v3 未対応リソース

README とナレッジ記事で、執筆時点の v3 未移植として挙げられているもの。

- `archive_share`
- `certificate_authority`
- `esme`
- `mobile_gateway`
- `sim`

これらを使っている場合は、一括 v3 移行ではなく以下を検討する。

- v3 対応済みリソースから段階移行する。
- 未対応リソースだけ v2 で一時的に管理する。
- Terraform 管理対象から外し、コントロールパネルや API で管理する。
- さくらのサポートに利用中リソース名・用途を添えて問い合わせる。

## 命名変更

Terraform resource / data source の type 名と Terraform `output` / variable / module interface 名は分けて扱う。
`output "sakuracloud_..."` のような公開名は downstream の参照 contract になり得るため、Provider prefix 変更に合わせて自動 rename しない。原則として公開名は維持し、`value` 側の resource 参照だけを v3 に更新する。

代表例:

| v2 | v3 |
| --- | --- |
| `sakuracloud_*` | `sakura_*` |
| `sakuracloud_switch` | `sakura_vswitch` |
| `sakuracloud_vpc_router` | `sakura_vpn_router` |
| `sakuracloud_proxylb` | `sakura_enhanced_lb` |
| `sakuracloud_note` | `sakura_script` |
| `sakuracloud_load_balancer` | `sakura_dsr_lb` |
| `sakuracloud_apprun_application` | `sakura_apprun_shared` |

属性名の代表例:

| v2 | v3 | 備考 |
| --- | --- | --- |
| `switch_id` | `vswitch_id` | `local_router` は対象が vswitch 以外もあり例外に注意 |
| `weekdays` | `days_of_week` | `auto_backup` など |
| `disabled` | `enabled` | `auto_scale`; 真偽が逆になる |

## data source の `filter` 廃止

v2:

```hcl
data "sakuracloud_disk" "example" {
  filter {
    names = ["Example"]
  }
}
```

v3:

```hcl
data "sakura_disk" "example" {
  name = "Example"
}
```

一般形:

```hcl
# v2
filter {
  id    = "xxxxxxxxxxxx"
  names = ["foobar"]
  tags  = ["foo", "bar"]
}

# v3
id   = "xxxxxxxxxxxx"
name = "foobar"
tags = ["foo", "bar"]
```

`names` は `name` になる点に注意する。

## Block から Attribute への変更

v3 では Terraform Plugin Framework の推奨に合わせ、過去 Block 構文だった nested field の多くが Attribute 構文になる。

単一 object:

```hcl
# v2
timeouts {
  create = "20m"
}

# v3
timeouts = {
  create = "20m"
}
```

list object:

```hcl
# v2
user {
  name = "user1"
}
user {
  name = "user2"
}

# v3
user = [
  { name = "user1" },
  { name = "user2" },
]
```

## リソース別注意点

### `apprun_shared` (`apprun_application` in v2)

- resource 名: `sakuracloud_apprun_application` → `sakura_apprun_shared`
- `components`: Block → List Attribute
- `components.deploy_source`: Block → Single Attribute
- `components.deploy_source.container_registry`: Block → Single Attribute
- `components.env`: Block/Set → Set Attribute
- `components.probe`: Block → Single Attribute
- `components.probe.http_get`: Block → Single Attribute
- `components.probe.http_get.headers`: Block/Set → Set Attribute
- `traffics`: Block → List Attribute
- `packet_filter`: Block → Single Attribute
- selected Provider schema が対応していれば `password_wo` / `password_wo_version` を優先。AppRun の `deploy_source.container_registry.password_wo` は `password_wo_version` と併せる。コンテナレジストリ認証の `password` も write-only 化し、password rotation 時に version を increment する運用変数を用意する。schema が未対応なら、まず最新 v3 patch への更新で対応できないか確認する。
- 同じ registry credential map を複数 component / resource に書く場合は local に集約し、version field の更新漏れを避ける。
- v2 で `dynamic "env"` のような nested dynamic block を使っている場合、v3 では `env = [for k, v in local.envs : { key = k, value = v }]` のような attribute 値生成へ変換する。

### `auto_backup`

- `weekdays` → `days_of_week`

### `auto_scale`

- `disabled` → `enabled`。真偽値が逆。
- `trigger_type` は必須。
- `router_threshold_scaling` / `cpu_threshold_scaling`: Block → Single Attribute
- `schedule_scaling`: Block → List Attribute

### `cdrom`

- `content` / `content_file_name` は削除。
- 事前に ISO を作り、`iso_image_file` を指定する。

### `container_registry`

- `user`: Block → Set/List Attribute
- `user.password_wo` が schema にある場合は `password_wo_version` と併せて使う。schema が `password` のみを要求する場合は、Provider version 更新で write-only 化できないか確認する。
- `access_level` は deprecated。v2 構成に `readwrite` などが残っている場合は、匿名アクセス要件を確認する。最新 v3 schema で任意属性なら、public/anonymous access を管理する明確な要件がない限り属性自体を削除する。古い v3 で required と出る場合は、まず Provider version の更新を検討する。

### `database`

- `switch_id` → `vswitch_id`
- `weekdays` → `days_of_week`
- `network_interface`: Block → Single Attribute
- `backup`: Block → Single Attribute
- selected Provider schema が対応していれば `password_wo` / `password_wo_version` を優先。field 名は schema / validate で確認する。

### `database_read_replica`

- `switch_id` → `vswitch_id`
- `network_interface`: Block → Single Attribute

### `dns`

- `record` field は削除。
- DNS レコードは `sakura_dns_record` リソースへ分離する。

### `dsr_lb` (`load_balancer` in v2)

- resource 名: `sakuracloud_load_balancer` → `sakura_dsr_lb`
- `switch_id` → `vswitch_id`
- `network_interface`: Block → Single Attribute
- `vip` / `server`: Block → List Attribute

### `enhanced_db`

- `password` から `password_wo` / `password_wo_version` へ変更。

### `enhanced_lb` (`proxylb` in v2)

- resource 名: `sakuracloud_proxylb` → `sakura_enhanced_lb`
- `health_check` / `sorry_server` / `syslog`: Block → Single Attribute
- `bind_port` / `server` / `rule`: Block → List Attribute

### `gslb`

- `health_check`: Block → Single Attribute
- `server`: Block → List Attribute

### `internet`

- `switch_id` → `vswitch_id`

### `local_router`

- `secret_keys` は将来的に値を持たなくなるため依存しない。
- `switch` / `network_interface`: Block → Single Attribute
- `static_route` / `peer`: Block → List Attribute

### `nfs`

- `switch_id` → `vswitch_id`
- `network_interface`: Block → Single Attribute

### `packet_filter`

- `expression` field は削除。
- rule は `sakura_packet_filter_rules` リソースへ分離する。

### `packet_filter_rules`

- `expression`: Block → List Attribute

### `server`

- `network_interface`: Block → List Attribute
- `disk_edit_parameter`: Block → Single Attribute
- `disk_edit_parameter.note_ids` は削除。代わりに `script` field を使う。
- selected Provider schema が対応していれば `password_wo` / `password_wo_version` を優先。field 名は schema / validate で確認する。

### `simple_monitor`

- `health_check`: Block → Single Attribute
- selected Provider schema が対応していれば `password_wo` / `password_wo_version` を優先。field 名は schema / validate で確認する。

### `subnet`

- `switch_id` → `vswitch_id`

### `vpn_router` (`vpc_router` in v2)

- resource 名: `sakuracloud_vpc_router` → `sakura_vpn_router`
- `switch_id` → `vswitch_id`
- `public_network_interface`: Block → Single Attribute
- `private_network_interface`: Block → List Attribute
- `dhcp_server`: Block → List Attribute
- `dhcp_static_mapping`: Block → List Attribute
- `dns_forwarding`: Block → Single Attribute
- `firewall` とその `expression`: Block → List Attribute
- `l2tp`: Block → Single Attribute
- `pptp`: Block → Single Attribute
- `port_forwarding`: Block → List Attribute
- `wire_guard`: Block → Single Attribute、その `peer` は List Attribute
- `site_to_site_vpn`: Block → List Attribute
- `site_to_site_vpn_parameter` と内部 nested field: Block → Single Attribute
- `static_nat`: Block → List Attribute
- `static_route`: Block → List Attribute
- `user`: Block → List Attribute
- `scheduled_maintenance`: Block → Single Attribute
- selected Provider schema が対応していれば `password_wo` / `password_wo_version` を優先。field 名は schema / validate で確認する。

### `webaccel`

古い v3 patch では WebAccel resource が未実装のことがある。`sakura_webaccel` / `sakura_webaccel_activation` / `sakura_webaccel_certificate` が見つからない場合、v2 継続と判断する前に最新 v3 patch の docs / schema を確認する。

属性名変更:

| v2 | v3 |
| --- | --- |
| `s3_endpoint` | `endpoint` |
| `s3_region` | `region` |
| `s3_bucket_name` | `bucket_name` |
| `s3_access_key_id` | `access_key_wo` |
| `s3_secret_access_key` | `secret_access_key_wo` |
| `s3_doc_index` | `use_document_index` |

- `access_key_wo` / `secret_access_key_wo` / `onetime_url_secrets_wo` は対応する version field と併せて指定する。
- `origin_parameters` / `logging`: Block → Single Attribute
- `cors_rules`: Block → Set/List Attribute

### `webaccel_certificate`

- `certificate_chain` → `certificate_chain_wo`
- `private_key` → `private_key_wo`
- `certificate_chain_wo` / `private_key_wo` は selected Provider schema の version field と併せて指定する。v3.12 系では `certificate_wo_version`。`certificate_chain_wo_version` / `private_key_wo_version` のように推測せず schema / validate で確認する。
- ACME renew などで証明書 material が変わっても、write-only field の version が変わらなければ再送されない。環境別の version 変数や runbook で rotation 時の increment を明示する。

## import / State 移行の注意

- 既存 State は v3 リソースとして自動認識されない。
- v3 resource 定義と `import` block を用意して既存実リソースを取り込む方法が基本候補。
- `terraform import` 後は、同じ実 resource の旧 v2 State address が残っていないか確認し、必要に応じて `terraform state rm` で State 管理から外す。二重管理のまま plan しない。
- import ID の形式は resource ごとに異なる可能性がある。Provider docs、既存 State、API / control panel で確認し、未確認の ID 形式を確定コマンドとして書かない。runbook では `<...>` placeholder と「要確認」を明示する。
- `terraform state show` は resource によって secret を表示し得る。AppRun env、registry credential、password 系を含む resource では全量出力を CI log / 共有 terminal / agent tool transcript に残さない。agent 上では全量 `state show` を実行せず、ユーザー許可の上で stdout に secret が出ない ID 抽出コマンドだけを使う。
- migration 用の確認フラグや guard resource を通常の Terraform graph に入れると、移行後の plan/apply に一時手順が残る。恒久的な graph ではなく、runbook / import block / plan review で制御する。
- Terraform の `-generate-config-out` は experimental。生成結果はテンプレートとして扱い、必ず確認・修正する。
- 再作成が必要な場合はサービス影響をユーザーと確認する。
- v2 継続時は、2026 年 12 月末メンテナンス終了後のリスクを明示する。
