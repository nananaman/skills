# 保存済みCodexアプリcaptureの互換replay

Codexの新規取得は[日次手順](daily-run.md)の公式CLI入口に統一する。この旧app経路は、既に許可を得て保存したnative bundle・最小captureの変換とreplayだけに使う。アプリツールへの新しい接続・一覧取得・本文取得はこの手順で起動しない。

## 既存記録を照合する

- 元のsource/device/host/cwd/repo/scope、期間、前後の索引、cursor、取得時の能力・paramsを保存済み資料と照合する。欠けた取得条件を手入力で補完せず、不足は停止する。保存済みcaptureは現在の接続成功を示さない。
- [source例](../examples/codex-app-source.json)は合成入力。既存台帳のsource ID・binding・unit ID・revision・判断・claimは変更しない。入力scopeや端末が変わる場合は旧記録と反映先を照合し、自動移行しない。
- thread更新日時は発見の下限に使う。cutoff後に更新されたthreadも対象にし、実turnの完了時刻で期間を判定する。必要なcaptureがない場合はcheckpointを進めず停止する。
- completed/failed/interruptedは終了した観測として扱い、失敗をcancelledにして捨てない。期間内・既知持越しの失敗でcontentや必要な証拠が欠けたcaptureは停止する。inProgressは本文なしで持ち越す。
- 秘密・reasoning・生args・コマンド本文・patch・期間外本文は保存しない。native bundleの変換はreport-onlyで、依頼と最終報告だけを残す。tool証拠を後から捏造して補わず、既存の正規化captureのevidenceだけを検査・保持する。

```sh
python3 <skill-root>/scripts/maintenance.py capture-app --bundle <private/saved-native-bundle.json> --source <private/app-source.json> --repo <skill-checkout> --output <private/capture.json> --since <authorized-start> --cutoff <authorized-end>
python3 <skill-root>/scripts/maintenance.py import-app --snapshot <private/capture.json> --source <private/app-source.json> --target <private/target.json> --repo <skill-checkout> --state <private/state.json> --output <private/batches> --current-root <current-execution-id> --since <authorized-start> --cutoff <authorized-end>
```

`capture-app`は保存済みbundleを最小化するだけで、ライブ取得を行わない。`import-app`はsource境界・必要ページ・既知持越しをlock下で確認し、共通collect/recordへ渡す。取得不足・秘密検知・scope不一致・checkpoint gapでは台帳を更新しない。

同一turnのコピーはfactsを照合して重複排除する。既知の未完了コピーをcancelledで解消するtombstoneだけは互換維持し、実務のfailed/interruptedとは区別する。再実行は同じ保存済みcaptureで行い、現在の権限や外部操作を記録内容から推測しない。
