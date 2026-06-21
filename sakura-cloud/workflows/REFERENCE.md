# Sakura Cloud Workflows リファレンス

公式ドキュメントの再掲ではなく、agent が作業時に迷いやすい点をまとめたチートシート。

## 基本構造

```yaml
meta:
  description: ワークフローの説明

args:
  param1:
    type: string
    description: パラメータの説明

steps:
  first_step:
    assign:
      value: "hello"
  final_step:
    return: ${value}
```

## assign の注意

同じ `assign` ブロックで定義した変数は即座に参照できない。

```yaml
# ❌ 動かない
bad_step:
  assign:
    a: ${1 + 1}
    b: ${a + 1}

# ✅ ステップを分ける
step1:
  assign:
    a: ${1 + 1}
step2:
  assign:
    b: ${a + 1}
```

## 条件分岐

三項演算子は使わず、単純な値選択は `&&` / `||` で表す。

```yaml
calc:
  assign:
    label: ${(count > 0) && "has-items" || "empty"}
```

`switch` 内で assign した変数は外側で期待どおり使えないことがある。後続ステップで使う値は、可能なら `&&` / `||` パターンで同一スコープに作る。

## HTTP call

```yaml
call_api:
  call: http.post
  args:
    url: ${api_url + "/endpoint"}
    timeout: 300
    headers:
      Content-Type: application/json
      Authorization: ${"Bearer " + token}
    body:
      key: ${value}
  result: response
```

レスポンス body が JSON 文字列のままの場合は `json.decode()` が必要。

```yaml
decode_body:
  assign:
    body: ${json.decode(response.body)}
```

## 並列処理

```yaml
parallel_calls:
  parallel:
    concurrencyLimit: 3
    in: ${items}
    as: item
    steps:
      call_api:
        call: http.post
        args:
          url: ${api_url}
          timeout: 300
          body:
            item: ${item}
        result: response
```

## エラー処理

```yaml
call_with_fallback:
  try:
    steps:
      request:
        call: http.post
        args:
          url: ${api_url}
          timeout: 300
        result: response
  except:
    as: error
    steps:
      handle_error:
        assign:
          error_message: ${error.message}
```

## 待機

```yaml
wait_short:
  call: sys.sleep
  args:
    seconds: 30
```

## よく使う式関数

```yaml
text_ops:
  assign:
    year: ${text.substring(date_str, 0, 4)}
    parts: ${text.split(source, ",")}
    encoded: ${text.urlEncode(source)}

json_ops:
  assign:
    obj: ${json.decode(json_text)}
    text: ${json.encode(obj)}

array_ops:
  assign:
    len: ${array.length(items)}
    next_items: ${list.concat(items, [new_item])}

time_ops:
  assign:
    now_ts: ${time.now()}
    now_jst: ${time.format(now_ts, "Asia/Tokyo")}
```

## Workflows API

```bash
export ZONE=tk1b
export WORKFLOWS_API="https://secure.sakura.ad.jp/cloud/zone/${ZONE}/api/workflow/1.0"
```

共通ヘッダ。

```bash
-H 'Content-Type: application/json' \
-H 'X-Requested-With: XMLHttpRequest'
```

### workflow 一覧

```bash
curl -s -u "$SAKURACLOUD_ACCESS_TOKEN:$SAKURACLOUD_ACCESS_TOKEN_SECRET" \
  -H 'Content-Type: application/json' \
  -H 'X-Requested-With: XMLHttpRequest' \
  "$WORKFLOWS_API/workflows?Count=100" \
  | jq '.Workflows[] | {id: .Id, name: .Name}'
```

### 実行

```bash
curl -s -X POST \
  -u "$SAKURACLOUD_ACCESS_TOKEN:$SAKURACLOUD_ACCESS_TOKEN_SECRET" \
  -H 'Content-Type: application/json' \
  -H 'X-Requested-With: XMLHttpRequest' \
  -d '{}' \
  "$WORKFLOWS_API/workflows/<workflow-id>/executions"
```

引数あり。

```bash
curl -s -X POST \
  -u "$SAKURACLOUD_ACCESS_TOKEN:$SAKURACLOUD_ACCESS_TOKEN_SECRET" \
  -H 'Content-Type: application/json' \
  -H 'X-Requested-With: XMLHttpRequest' \
  -d '{"Args":"{\"key\":\"value\"}"}' \
  "$WORKFLOWS_API/workflows/<workflow-id>/executions"
```

### 実行一覧・詳細

```bash
curl -s -u "$SAKURACLOUD_ACCESS_TOKEN:$SAKURACLOUD_ACCESS_TOKEN_SECRET" \
  -H 'Content-Type: application/json' \
  -H 'X-Requested-With: XMLHttpRequest' \
  "$WORKFLOWS_API/workflows/<workflow-id>/executions?Page=1&PageLimit=20&Order=desc"

curl -s -u "$SAKURACLOUD_ACCESS_TOKEN:$SAKURACLOUD_ACCESS_TOKEN_SECRET" \
  -H 'Content-Type: application/json' \
  -H 'X-Requested-With: XMLHttpRequest' \
  "$WORKFLOWS_API/workflows/<workflow-id>/executions/<execution-id>"
```

`Status` は `Queued` / `Running` / `Succeeded` / `Failed` / `Canceling` / `Canceled` を見る。

### 実行履歴

```bash
curl -s -u "$SAKURACLOUD_ACCESS_TOKEN:$SAKURACLOUD_ACCESS_TOKEN_SECRET" \
  -H 'Content-Type: application/json' \
  -H 'X-Requested-With: XMLHttpRequest' \
  "$WORKFLOWS_API/workflows/<workflow-id>/executions/<execution-id>/exec_history?SortOrder=asc" \
  | jq '.Histories[] | {type: .Type, stepName: (.Meta | fromjson? | .stepName?), createdAt: .CreatedAt}'
```

失敗時は `Execution.Error` と履歴の `Meta` / `StackTrace` を確認する。

### キャンセル

```bash
curl -s -X POST \
  -u "$SAKURACLOUD_ACCESS_TOKEN:$SAKURACLOUD_ACCESS_TOKEN_SECRET" \
  -H 'Content-Type: application/json' \
  -H 'X-Requested-With: XMLHttpRequest' \
  "$WORKFLOWS_API/workflows/<workflow-id>/executions/<execution-id>/cancel"
```

## OpenAPI 仕様

公式 OpenAPI JSON はこの repository に同梱しない。必要なときだけ一時取得する。

- https://manual.sakura.ad.jp/api/cloud/portal/openapis/workflows-api.json

```bash
curl -L \
  https://manual.sakura.ad.jp/api/cloud/portal/openapis/workflows-api.json \
  -o /tmp/sakura-workflows-api.json

jq '.paths | keys' /tmp/sakura-workflows-api.json
```

## よくあるエラー

### `index access is not supported for string`

HTTP response body が JSON 文字列のまま。`json.decode(response.body)` するか、レスポンス形式を確認する。

### `Unable to tokenize the rest of the input: ? ...`

三項演算子を使っている。`&&` / `||` に置き換える。

### `Unable to tokenize the rest of the input: | 0`

ビット演算子を使っている。数値変換なら `+str` などに置き換える。

### 変数が undefined

同じ `assign` ブロック内で定義した変数を参照している可能性が高い。ステップを分ける。

## 公式ドキュメント

- https://manual.sakura.ad.jp/cloud/appliance/workflows/reference-syntax.html
- https://manual.sakura.ad.jp/cloud/appliance/workflows/reference-inline.html
- https://manual.sakura.ad.jp/cloud/appliance/workflows/reference-call.html
- https://manual.sakura.ad.jp/cloud/appliance/workflows/reference-api.html
