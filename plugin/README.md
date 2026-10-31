# nananaman pstack supplement

Codexでpstackを標準の開発フローとして使うための日本語規約と専門知識です。
汎用の計画、設計、実装、TDD、レビュー、PR進行、振り返りはpstackに集約します。
このpackageは第二のrouterや自動学習処理を提供しません。

補完packageは `nananaman-pstack-supplement` version `0.3.0`、pstack依存は `0.9.114` の固定commitです。
今回の差分は移行準備であり、稼働中の旧pluginや設定を切り替えていません。

## Engineering

- [apple-container](./skills/apple-container/SKILL.md)
- [excalidraw](./skills/excalidraw/SKILL.md)
- [nono-sandbox-maintenance](./skills/nono-sandbox-maintenance/SKILL.md)
- [test-writing-style](./skills/test-writing-style/SKILL.md)

## Meta

- [apm-usage](./skills/apm-usage/SKILL.md)
- [skill-workbench](./skills/skill-workbench/SKILL.md)
- [update-skills](./skills/update-skills/SKILL.md)

## Personal

- [chouge-git](./skills/chouge-git/SKILL.md)

## Sakura Cloud

- [sakura-cloud-eventbus](./skills/sakura-cloud-eventbus/SKILL.md)
- [sakura-cloud-webaccel](./skills/sakura-cloud-webaccel/SKILL.md)
- [sakura-cloud-workflows](./skills/sakura-cloud-workflows/SKILL.md)

## Writing

- [chouge-changelog](./skills/chouge-changelog/SKILL.md)
- [chouge-writing](./skills/chouge-writing/SKILL.md)

## 導入条件

このpackageはpstack本体を含みません。
旧汎用APM依存は除き、各利用環境でpstackの名前・資材・モデル・hookの対応を確認します。
pstackと同じ環境で使用します。通常導入はdotfilesのAPM manifestを使い、native配布形式は必須にしません。global切替は検証・承認後に行います。
未導入時に旧汎用フローへ自動fallbackしません。
[移行手順](../docs/pstack-migration.md)と[固定版](../pstack.lock.json)はrepository rootにあります。
ZIPでこのpluginだけを受け取った場合、これらはrepositoryの同じ版を参照してください。

`skill-workbench`は明示的な評価依頼専用です。
新しい履歴収集、日次振り返り、reflectの自動適用は行いません。
各専門skillのOS、CLI、認証、操作権限条件は個別に確認します。
