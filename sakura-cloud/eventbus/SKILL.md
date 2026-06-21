---
name: sakura-cloud-eventbus
description: さくらのクラウド EventBus の実行設定、スケジュール、イベントトリガーを設計・作成・確認する。SimpleMQ / シンプル通知への定期実行やイベント駆動実行を扱うときに使用。
---

# Sakura Cloud EventBus

さくらのクラウド EventBus で、定期実行またはクラウドイベントを契機に外部サービスを呼び出すための作業ランブック。

## まず確認すること

- 実行したい契機はどちらか。
  - 定期実行: `Schedule`
  - イベント検知: `Trigger`
- 呼び出し先はどれか。
  - シンプル通知: `simplenotification`
  - シンプルMQ: `simplemq`
  - オートスケール: `autoscale`
- API 操作に使う zone はどこか。
  - 例: `is1a`, `is1b`, `is1c`, `tk1a`, `tk1b`

## 作業順

1. 既存の `ProcessConfiguration` / `Schedule` / `Trigger` を一覧取得する。
   - 再利用できる設定がないか確認する。
2. `ProcessConfiguration` を作る。
   - 何を呼び出すかを定義する。
3. `Schedule` または `Trigger` を作る。
   - いつ呼び出すかを定義する。
   - 時刻指定では timezone の解釈を確認し、未確認なら作成前に止まる。
4. 作成後に一覧取得で ID と設定内容を確認する。

## 安全ゲート

- 作成・更新・削除の API を実行する前に、対象 zone、対象 ID、作成/変更内容、影響範囲をユーザーに提示する。
- ユーザーの明示承認があるまで、`POST` / `PUT` / `DELETE` は実行しない。

## 認証

Sakura Cloud API は Basic 認証を使う。

```bash
curl -u "$SAKURACLOUD_ACCESS_TOKEN:$SAKURACLOUD_ACCESS_TOKEN_SECRET" \
  -H 'Content-Type: application/json' \
  "https://secure.sakura.ad.jp/cloud/zone/${ZONE}/api/cloud/1.1/commonserviceitem/"
```

認証情報の取得方法は各プロジェクトの secrets 運用に従う。この skill には特定プロジェクトの vault 名や item 名を置かない。

## よくある落とし穴

- `ProcessConfiguration` を削除する前に、利用中の `Schedule` / `Trigger` を削除する。
- `Settings.Parameters` は JSON 文字列として渡す必要がある。
- スケジュールはベストエフォートで、厳密なリアルタイム実行を保証しない。
- 最小スケジュール間隔は 1 分。

## 詳細

API 例、設定 JSON、イベントタイプの代表例は [REFERENCE.md](REFERENCE.md) を参照する。
公式仕様の網羅確認が必要な場合は、末尾の公式ドキュメントを参照する。
