---
name: sakura-cloud-workflows
description: さくらのクラウド Workflows の YAML 作成、式のデバッグ、HTTP/API 呼び出し、実行履歴確認、失敗調査、キャンセルを扱うときに使用。
---

# Sakura Cloud Workflows

さくらのクラウド Workflows の runbook 作成・デバッグ・API 操作のための作業ランブック。

## まず確認すること

- 目的はどれか。
  - YAML runbook を作る
  - 既存 runbook の構文・式を直す
  - 実行履歴や失敗理由を確認する
  - API から workflow を作成・実行・キャンセルする
- 認証情報は環境変数に展開済みか。
  - `SAKURACLOUD_ACCESS_TOKEN`
  - `SAKURACLOUD_ACCESS_TOKEN_SECRET`
- 対象 zone はどこか。例では `tk1b` を使う。

## YAML 作成後の確認

- `assign` の同一ブロック参照、式構文、HTTP response body の decode 要否を `REFERENCE.md` の落とし穴に照らして確認する。
- 公式の検証 API や dry-run が使えるか不明な場合は、いきなり本番実行せず、実行前レビュー用の YAML と確認観点をユーザーに提示する。

## 安全ゲート

- workflow 作成・実行・キャンセルの前に、対象 zone、workflow ID、execution ID、引数、影響範囲をユーザーに提示する。
- ユーザーの明示承認があるまで、作成・実行・キャンセル API は実行しない。
- 公式 OpenAPI JSON を確認する場合は `/tmp` などに一時取得し、この repository には保存しない。

## 認証

Workflows API は Basic 認証を使う。

```bash
curl -u "$SAKURACLOUD_ACCESS_TOKEN:$SAKURACLOUD_ACCESS_TOKEN_SECRET" \
  -H 'Content-Type: application/json' \
  -H 'X-Requested-With: XMLHttpRequest' \
  "https://secure.sakura.ad.jp/cloud/zone/tk1b/api/workflow/1.0/workflows?Count=100"
```

認証情報の取得方法は各プロジェクトの secrets 運用に従う。この skill には特定プロジェクトの vault 名や item 名を置かない。

## 最重要の落とし穴

Workflows の式は JavaScript ではない。次は使えない。

```yaml
# ❌ 三項演算子
value: ${condition ? trueVal : falseVal}

# ❌ ビット演算子
value: ${num | 0}

# ❌ JavaScript 組み込み関数
value: ${parseInt(str)}
value: ${String(num)}
value: ${Math.floor(num)}
```

代替する。

```yaml
# ✅ 条件分岐は && / ||
value: ${(condition) && trueVal || falseVal}

# ✅ 文字列→数値
num: ${+str}

# ✅ 数値→文字列
str: ${"" + num}
```

さらに、同じ `assign` ブロックで定義した変数はその場で参照できない。ステップを分ける。

## 詳細

YAML 構文、式関数、実行履歴確認、API 操作例、OpenAPI URL は [REFERENCE.md](REFERENCE.md) を参照する。
公式 OpenAPI JSON はこの skill repository に同梱しない。必要時に公式 URL から一時取得する。
