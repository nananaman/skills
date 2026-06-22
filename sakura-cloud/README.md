# Sakura Cloud Skills

さくらのクラウド関連サービスを扱うための domain runbook 群です。
対象サービスの API 作法、安全ゲート、Terraform / API の使い分けを agent が参照できるようにします。

## どの Skill を使うか

- EventBus の Schedule / Trigger / ProcessConfiguration を扱う → [`sakura-cloud-eventbus`](./eventbus/SKILL.md)
- ウェブアクセラレータのサイト設定、独自ドメイン、SSL、キャッシュ削除を扱う → [`sakura-cloud-webaccel`](./webaccel/SKILL.md)
- Workflows の YAML、式、HTTP/API 呼び出し、実行履歴を扱う → [`sakura-cloud-workflows`](./workflows/SKILL.md)

## 典型フロー

1. 対象サービスに対応する skill を読み、必要な zone・認証情報・管理元を確認する。
2. 作成・更新・削除・実行など影響のある API 操作前に、安全ゲートに従って対象と影響範囲を提示する。
3. ユーザーの明示承認を得てから変更系操作を実行し、実行後に一覧取得や履歴確認で結果を検証する。

## Skill 一覧

- **[`sakura-cloud-eventbus`](./eventbus/SKILL.md)** — EventBus の実行設定、スケジュール、イベントトリガーを扱う。
  - Use when: EventBus 設計、Schedule / Trigger 作成、SimpleMQ / シンプル通知連携
  - Type: `model-invoked`
- **[`sakura-cloud-webaccel`](./webaccel/SKILL.md)** — ウェブアクセラレータのサイト設定・運用を扱う。
  - Use when: サイト追加、独自ドメイン / SSL 設定、キャッシュ削除 / オリジンガード
  - Type: `model-invoked`
- **[`sakura-cloud-workflows`](./workflows/SKILL.md)** — Workflows の YAML 作成、デバッグ、API 操作を扱う。
  - Use when: YAML 作成、式のデバッグ、実行履歴確認 / キャンセル
  - Type: `model-invoked`
