# Sakura Cloud WebAccel リファレンス

公式ドキュメントの再掲ではなく、agent が作業時に迷いやすい点をまとめたチートシート。

## API 基本

```bash
export WEBACCEL_API="https://secure.sakura.ad.jp/cloud/zone/is1a/api/webaccel/1.0"
```

`X-Requested-With: XMLHttpRequest` を付ける。

```bash
curl -u "$SAKURACLOUD_ACCESS_TOKEN:$SAKURACLOUD_ACCESS_TOKEN_SECRET" \
  -H 'X-Requested-With: XMLHttpRequest' \
  "$WEBACCEL_API/site"
```

## サイト作成

```bash
curl -X POST \
  -u "$SAKURACLOUD_ACCESS_TOKEN:$SAKURACLOUD_ACCESS_TOKEN_SECRET" \
  -H 'Content-Type: application/json' \
  -H 'X-Requested-With: XMLHttpRequest' \
  -d '{
    "Site": {
      "Name": "example-cdn",
      "DomainType": "own_domain",
      "Domain": "cdn.example.com",
      "Origin": "origin.example.com"
    }
  }' \
  "$WEBACCEL_API/site"
```

作成後はサイト詳細を取得し、CNAME / TXT 認証値 / status を確認する。

```bash
curl -u "$SAKURACLOUD_ACCESS_TOKEN:$SAKURACLOUD_ACCESS_TOKEN_SECRET" \
  -H 'X-Requested-With: XMLHttpRequest' \
  "$WEBACCEL_API/site/<site-id>"
```

## サイト有効化・無効化

有効化。

```bash
curl -X PUT \
  -u "$SAKURACLOUD_ACCESS_TOKEN:$SAKURACLOUD_ACCESS_TOKEN_SECRET" \
  -H 'Content-Type: application/json' \
  -H 'X-Requested-With: XMLHttpRequest' \
  -d '{"Site":{"Status":"enabled"}}' \
  "$WEBACCEL_API/site/<site-id>/status"
```

無効化。

```bash
curl -X PUT \
  -u "$SAKURACLOUD_ACCESS_TOKEN:$SAKURACLOUD_ACCESS_TOKEN_SECRET" \
  -H 'Content-Type: application/json' \
  -H 'X-Requested-With: XMLHttpRequest' \
  -d '{"Site":{"Status":"disabled"}}' \
  "$WEBACCEL_API/site/<site-id>/status"
```

## キャッシュ削除

全件削除。

```bash
curl -X DELETE \
  -u "$SAKURACLOUD_ACCESS_TOKEN:$SAKURACLOUD_ACCESS_TOKEN_SECRET" \
  -H 'X-Requested-With: XMLHttpRequest' \
  "$WEBACCEL_API/site/<site-id>/cache"
```

URL 単位の削除。

```bash
curl -X DELETE \
  -u "$SAKURACLOUD_ACCESS_TOKEN:$SAKURACLOUD_ACCESS_TOKEN_SECRET" \
  -H 'Content-Type: application/json' \
  -H 'X-Requested-With: XMLHttpRequest' \
  -d '{"URLs":["https://cdn.example.com/assets/app.css"]}' \
  "$WEBACCEL_API/deletecache"
```

制限:

- 一度に 100 URL まで。
- 1 時間あたり 500 URL まで。

## SSL 証明書

Let's Encrypt を有効化する例。

```bash
curl -X POST \
  -u "$SAKURACLOUD_ACCESS_TOKEN:$SAKURACLOUD_ACCESS_TOKEN_SECRET" \
  -H 'X-Requested-With: XMLHttpRequest' \
  "$WEBACCEL_API/site/<site-id>/certificate/letsencrypt"
```

持ち込み証明書の場合は秘密鍵を扱うため、コマンド履歴やログに出さない。必要なら request body を一時ファイルに置き、作業後に削除する。

## オリジンガード

トークン発行。

```bash
curl -X POST \
  -u "$SAKURACLOUD_ACCESS_TOKEN:$SAKURACLOUD_ACCESS_TOKEN_SECRET" \
  -H 'X-Requested-With: XMLHttpRequest' \
  "$WEBACCEL_API/site/<site-id>/originguard"
```

Nginx 側の例。

```nginx
if ($http_x_webaccel_guard != "YOUR_TOKEN") {
    return 403;
}
```

ローテーション中は現行・次期トークンの両方を一時的に許可する。

## DNS

独自ドメインでは、TXT 認証と CNAME を設定する。

```text
_webaccel.cdn.example.com  TXT    "webaccel=********.user.webaccel.jp"
cdn.example.com            CNAME  ********.user.webaccel.jp
```

A レコードと CNAME は共存できない。切り替え前に TTL を短くしておく。

## キャッシュ制御

WebAccel ではオリジンの `Cache-Control: s-maxage=...` を優先する。

```nginx
location ~* \.(jpg|jpeg|png|gif|webp|css|js)$ {
    add_header Cache-Control "s-maxage=86400, max-age=3600, public";
}

location ~* \.html$ {
    add_header Cache-Control "no-store, no-cache";
}
```

`Set-Cookie` があるレスポンスはキャッシュされない可能性があるため、意図しない Cookie を出していないか確認する。

## Terraform 最小例

詳細な引数一覧は公式 provider docs を参照する。ここでは構成の形だけ示す。

```hcl
terraform {
  required_providers {
    sakuracloud = {
      source  = "sacloud/sakuracloud"
      version = "~> 2.25"
    }
  }
}

provider "sakuracloud" {}

resource "sakuracloud_webaccel" "cdn" {
  name              = "example-cdn"
  domain_type       = "own_domain"
  request_protocol  = "https-redirect"
  default_cache_ttl = 86400

  origin_parameters {
    type     = "web"
    origin   = "origin.example.com"
    protocol = "https"
  }
}

resource "sakuracloud_webaccel_activation" "cdn" {
  site_id = sakuracloud_webaccel.cdn.id
  enabled = true
}
```

## トラブルシュート

### キャッシュされない

- `Cache-Control` に `private`, `no-store`, `no-cache` がないか。
- `Set-Cookie` が付いていないか。
- URL / query string / `Vary` の扱いが期待どおりか。

### オリジンガードで 403

- `X-WebAccel-Guard` のヘッダ名が正しいか。
- トークンに余計な空白がないか。
- ローテーション中なら現行・次期トークンの両方を許可しているか。

### DNS が切り替わらない

- TTL を確認する。
- A レコードが残っていないか確認する。
- negative cache を避けるため、削除と追加の順序に注意する。

## 公式ドキュメント

- https://manual.sakura.ad.jp/cloud/webaccel/webaccel.html
- https://manual.sakura.ad.jp/cloud/webaccel/manual/usage-guidance.html
- https://manual.sakura.ad.jp/cloud/webaccel/api.html
- https://manual.sakura.ad.jp/cloud/webaccel/manual/settings-originguard.html
- https://manual.sakura.ad.jp/cloud/webaccel/manual/settings-domain-ssl.html
- https://manual.sakura.ad.jp/cloud/webaccel/manual/faq.html
- https://docs.usacloud.jp/terraform/r/webaccel/
- https://docs.usacloud.jp/terraform/r/webaccel_certificate/
