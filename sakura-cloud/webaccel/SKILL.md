---
name: sakura-cloud-webaccel
description: さくらのウェブアクセラレータ（CDN）のサイト追加、独自ドメイン設定、キャッシュ削除、オリジンガード、SSL 証明書、Terraform 設定を扱うときに使用。
---

# Sakura Cloud WebAccel

さくらのウェブアクセラレータを設定・運用するための作業ランブック。

## 対象を確認する

依頼・既存設定から分かる情報は使い、今回の操作に必要な不足だけを質問する。

- ドメイン方式
  - 独自ドメイン
  - 新規サブドメイン
  - `*.user.webaccel.jp`
- オリジン種別
  - Web サーバ
  - オブジェクトストレージ
- HTTPS 方針
  - Let's Encrypt 自動証明書
  - 持ち込み証明書
  - HTTP のみ、または HTTPS への転送
- キャッシュ削除が必要か
- オリジンガードを使うか

## API / Terraform の使い分け

- 恒久的なサイト設定は Terraform 管理を優先する。
- 既存 Terraform 管理のサイトを API で直接変更すると二重管理になりやすい。先に管理元を確認する。
- キャッシュ削除など即時運用は API を使う。

## 外部操作の権限

- サイト作成・有効化・無効化・キャッシュ削除・証明書変更には、サイトID・ドメイン・操作・影響範囲への明示的な許可が必要。同じ範囲の会話内の許可は引き継ぐ。未許可なら具体的な案を示し、API書込みを保留する。
- 全件キャッシュ削除やサイト無効化では、指定URL範囲または対象サイトが許可範囲と一致することを確認する。範囲が変わる場合は改めて確認する。

## API の基本

WebAccel API は `is1a` のエンドポイントを使う。

```bash
export WEBACCEL_API="https://secure.sakura.ad.jp/cloud/zone/is1a/api/webaccel/1.0"

curl -u "$SAKURACLOUD_ACCESS_TOKEN:$SAKURACLOUD_ACCESS_TOKEN_SECRET" \
  -H 'X-Requested-With: XMLHttpRequest' \
  "$WEBACCEL_API/site"
```

認証情報の取得方法は各プロジェクトの機密情報の運用に従う。この skill には特定プロジェクトの保管庫名や項目名を置かない。

## よくある落とし穴

- WebAccel API はゾーンを常に `is1a` にする。他のゾーンのエンドポイントではない。
- URL 単位のキャッシュ削除は一度に 100 件まで、1 時間あたり 500 件まで。
- 独自ドメインでは CNAME と A レコードは共存できない。
- オリジンガードのトークン更新時は、移行中だけ現行・次期トークンを両方許可する。
- `Set-Cookie` や `Cache-Control` によりキャッシュされないことがある。

## 詳細

API 例、DNS、オリジンガード、Terraform の最小例は [REFERENCE.md](REFERENCE.md) を参照する。
公式仕様の網羅確認が必要な場合は、末尾の公式ドキュメントを参照する。
