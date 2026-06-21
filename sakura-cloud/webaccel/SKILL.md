---
name: sakura-cloud-webaccel
description: さくらのウェブアクセラレータ（CDN）のサイト追加、独自ドメイン設定、キャッシュ削除、オリジンガード、SSL 証明書、Terraform 設定を扱うときに使用。
---

# Sakura Cloud WebAccel

さくらのウェブアクセラレータを設定・運用するための作業ランブック。

## まず確認すること

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
  - HTTP のみ / HTTPS redirect
- キャッシュ削除が必要か
- オリジンガードを使うか

## API / Terraform の使い分け

- 恒久的なサイト設定は Terraform 管理を優先する。
- 既存 Terraform 管理のサイトを API で直接変更すると二重管理になりやすい。先に管理元を確認する。
- キャッシュ削除など即時運用は API を使う。

## 安全ゲート

- サイト作成・有効化・無効化・キャッシュ削除・証明書変更の前に、対象 site ID / domain、操作内容、影響範囲をユーザーに提示する。
- ユーザーの明示承認があるまで、`POST` / `PUT` / `DELETE` は実行しない。
- 全件キャッシュ削除やサイト無効化は特に影響が大きいため、URL 範囲または対象サイトを再確認する。

## API の基本

WebAccel API は `is1a` endpoint を使う。

```bash
export WEBACCEL_API="https://secure.sakura.ad.jp/cloud/zone/is1a/api/webaccel/1.0"

curl -u "$SAKURACLOUD_ACCESS_TOKEN:$SAKURACLOUD_ACCESS_TOKEN_SECRET" \
  -H 'X-Requested-With: XMLHttpRequest' \
  "$WEBACCEL_API/site"
```

認証情報の取得方法は各プロジェクトの secrets 運用に従う。この skill には特定プロジェクトの vault 名や item 名を置かない。

## よくある落とし穴

- WebAccel API は zone を常に `is1a` にする。他 zone の endpoint ではない。
- URL 単位のキャッシュ削除は一度に 100 件まで、1 時間あたり 500 件まで。
- 独自ドメインでは CNAME と A レコードは共存できない。
- オリジンガードのトークン更新時は、移行中だけ現行・次期トークンを両方許可する。
- `Set-Cookie` や `Cache-Control` によりキャッシュされないことがある。

## 詳細

API 例、DNS、オリジンガード、Terraform の最小例は [REFERENCE.md](REFERENCE.md) を参照する。
公式仕様の網羅確認が必要な場合は、末尾の公式ドキュメントを参照する。
