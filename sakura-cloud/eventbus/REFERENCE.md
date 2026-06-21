# Sakura Cloud EventBus リファレンス

公式ドキュメントの再掲ではなく、agent が作業時に迷いやすい点をまとめたチートシート。

## API 基本

```bash
export ZONE=is1a
export EVENTBUS_API="https://secure.sakura.ad.jp/cloud/zone/${ZONE}/api/cloud/1.1/commonserviceitem"
```

`Provider.Class` で対象を絞る。

| 対象 | Provider.Class |
| --- | --- |
| 実行設定 | `eventbusprocessconfiguration` |
| スケジュール | `eventbusschedule` |
| トリガー | `eventbustrigger` |

## 実行設定: ProcessConfiguration

SimpleMQ へ送る例。

```bash
curl -X POST \
  -u "$SAKURACLOUD_ACCESS_TOKEN:$SAKURACLOUD_ACCESS_TOKEN_SECRET" \
  -H 'Content-Type: application/json' \
  -d '{
    "CommonServiceItem": {
      "Name": "alert-to-mq",
      "Settings": {
        "Destination": "simplemq",
        "Parameters": "{\"queue_name\":\"alerts\",\"content\":\"alert\"}"
      },
      "Provider": {"Class": "eventbusprocessconfiguration"}
    }
  }' \
  "$EVENTBUS_API/"
```

シンプル通知へ送る場合は `Destination` を `simplenotification` にし、`Parameters` に通知先グループ ID とメッセージを入れる。

## スケジュール: Schedule

```bash
curl -X POST \
  -u "$SAKURACLOUD_ACCESS_TOKEN:$SAKURACLOUD_ACCESS_TOKEN_SECRET" \
  -H 'Content-Type: application/json' \
  -d '{
    "CommonServiceItem": {
      "Name": "daily-schedule",
      "Settings": {
        "ProcessConfigurationID": "<process-configuration-id>",
        "Crontab": "0 0 * * *",
        "StartsAt": 1700000000000
      },
      "Provider": {"Class": "eventbusschedule"}
    }
  }' \
  "$EVENTBUS_API/"
```

`StartsAt` は epoch milliseconds。`Crontab` を使わない場合は `RecurringStep` と `RecurringUnit` を指定する。

間隔指定の最小例。

```json
{
  "Settings": {
    "ProcessConfigurationID": "<process-configuration-id>",
    "RecurringStep": 5,
    "RecurringUnit": "minutes",
    "StartsAt": 1700000000000
  }
}
```

`RecurringUnit` は `minutes` / `hours` / `days` を使う。

## トリガー: Trigger

サーバ作成イベントを拾う例。

```bash
curl -X POST \
  -u "$SAKURACLOUD_ACCESS_TOKEN:$SAKURACLOUD_ACCESS_TOKEN_SECRET" \
  -H 'Content-Type: application/json' \
  -d '{
    "CommonServiceItem": {
      "Name": "server-created-trigger",
      "Settings": {
        "Source": "//eventbus.sakura.ad.jp/eventlog",
        "ProcessConfigurationID": "<process-configuration-id>",
        "Types": ["jp.ad.sakura.eventbus.eventlog.IaaS.request.Server.created"],
        "Conditions": [
          {"Key": "zone", "Op": "in", "Values": ["is1a", "tk1b"]}
        ]
      },
      "Provider": {"Class": "eventbustrigger"}
    }
  }' \
  "$EVENTBUS_API/"
```

代表的な `Source`:

| Source | 用途 |
| --- | --- |
| `//eventbus.sakura.ad.jp/monitoringsuite/alert` | モニタリングスイートのアラート |
| `//eventbus.sakura.ad.jp/eventlog` | クラウド操作イベント |

## 一覧・参照・削除

```bash
# 実行設定一覧
curl -u "$SAKURACLOUD_ACCESS_TOKEN:$SAKURACLOUD_ACCESS_TOKEN_SECRET" \
  "$EVENTBUS_API/?{\"Filter\":{\"Provider.Class\":[\"eventbusprocessconfiguration\"]}}"

# 参照
curl -u "$SAKURACLOUD_ACCESS_TOKEN:$SAKURACLOUD_ACCESS_TOKEN_SECRET" \
  "$EVENTBUS_API/<common-service-item-id>"

# 削除
curl -X DELETE \
  -u "$SAKURACLOUD_ACCESS_TOKEN:$SAKURACLOUD_ACCESS_TOKEN_SECRET" \
  "$EVENTBUS_API/<common-service-item-id>"
```

## チェックリスト

- [ ] `Parameters` が JSON 文字列として正しく escape されている。
- [ ] `ProcessConfigurationID` が実在する。
- [ ] `Trigger` の `Types` と `Conditions` が対象イベントに合っている。
- [ ] 削除時は `Schedule` / `Trigger` → `ProcessConfiguration` の順にする。

## 公式ドキュメント

- https://manual.sakura.ad.jp/cloud/appliance/eventbus/index.html
- https://manual.sakura.ad.jp/cloud/appliance/eventbus/basic.html
- https://manual.sakura.ad.jp/cloud/appliance/eventbus/control_panel.html
- https://manual.sakura.ad.jp/cloud/appliance/eventbus/events.html
- https://manual.sakura.ad.jp/cloud/appliance/eventbus/examples.html
