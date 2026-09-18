# 参照情報

調査日: 2026-06-23

## 公式・準公式ページ

- さくらのナレッジ: Terraform Provider v3 正式リリースと移行のポイント
  - https://knowledge.sakura.ad.jp/51008/
  - v3 の変更概要、v2 からの移行観点、State/import の考え方。
- さくらのクラウドニュース: Terraform Provider v2 メンテナンス終了のお知らせ
  - https://cloud.sakura.ad.jp/news/2026/06/23/terraform-provider-v2-end-of-maintenance/
  - v2 は 2026 年 12 月末でメンテナンス終了。2027 年 1 月以降は新機能追加、不具合修正、既存リソース改善を原則行わない。
- さくらのクラウド マニュアル: Terraform for さくらのクラウド
  - https://manual.sakura.ad.jp/cloud/tool/terraform/index.html
  - v3: `sacloud/sakura`、v2: `sacloud/sakuracloud`。新規利用は v3 推奨。v3 は一部未実装リソースあり。
- terraform-provider-sakura README / CHANGES
  - https://github.com/sacloud/terraform-provider-sakura
  - https://github.com/sacloud/terraform-provider-sakura/blob/main/CHANGES.md
  - v3 の変更点、未対応リソース、リソース別 migration note。
- Terraform Registry: v3 Provider docs
  - https://registry.terraform.io/providers/sacloud/sakura/latest/docs
- Terraform Registry: v2 Provider docs
  - https://registry.terraform.io/providers/sacloud/sakuracloud/latest/docs
- Terraform import config generation
  - https://developer.hashicorp.com/terraform/language/import/generating-configuration

## Provider 基本情報

### v2

```hcl
terraform {
  required_providers {
    sakuracloud = {
      source = "sacloud/sakuracloud"
      version = "~> 2"
    }
  }
}

provider "sakuracloud" {
  zone = "tk1b"
}
```

### v3

```hcl
terraform {
  required_providers {
    sakura = {
      source  = "sacloud/sakura"
      version = "~> 3"
    }
  }
}

provider "sakura" {
  zone = "tk1b"
}
```

上の `version = "~> 3"` は Provider 名の例示であり、移行時の固定方針ではない。
実移行では対象 resource が実装済みの最新 v3 patch を確認し、patch version pin または `.terraform.lock.hcl` の commit で検証済み version を固定する。`.terraform.lock.hcl` が repository で ignore されている場合は、lock file commit では固定できないため Provider block の exact version pin を使う。最新 patch は推測せず、一時的な `version = "~> 3"` と fresh `TF_DATA_DIR` の `terraform init -backend=false -upgrade`、または Registry / release 情報で確認する。

Terraform Registry の v3 docs では Terraform 1.11 以降対応とされている。

## 認証・環境変数

v3 Provider docs では、`token` / `secret` / `zone` などは `SAKURA_*` と従来の `SAKURACLOUD_*` の両方から取得できる項目がある。

例:

- `SAKURA_ACCESS_TOKEN` / `SAKURACLOUD_ACCESS_TOKEN`
- `SAKURA_ACCESS_TOKEN_SECRET` / `SAKURACLOUD_ACCESS_TOKEN_SECRET`
- `SAKURA_ZONE` / `SAKURACLOUD_ZONE`
- `SAKURA_DEFAULT_ZONE` / `SAKURACLOUD_DEFAULT_ZONE`

移行時は既存 CI/CD secrets が `SAKURACLOUD_*` のまま使えるか Provider docs で確認する。新規設定では `SAKURA_*` への統一も検討する。
