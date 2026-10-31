# nananaman pstack supplement

Codexでpstackを標準の開発フローとして使うための日本語規約と専門知識です。
汎用の計画、設計、実装、TDD、レビュー、PR進行、振り返りはpstackに集約します。
このpackageは第二のrouterや自動学習処理を提供しません。

補完packageは `nananaman-pstack-supplement` version `0.3.0`、pstack依存は `0.9.114` の固定commitです。
今回の差分は移行準備であり、稼働中の旧pluginや設定を切り替えていません。

## Engineering

- [apple-container](./plugin/skills/apple-container/SKILL.md)
- [excalidraw](./plugin/skills/excalidraw/SKILL.md)
- [nono-sandbox-maintenance](./plugin/skills/nono-sandbox-maintenance/SKILL.md)
- [test-writing-style](./plugin/skills/test-writing-style/SKILL.md)

## Meta

- [apm-usage](./plugin/skills/apm-usage/SKILL.md)
- [skill-workbench](./plugin/skills/skill-workbench/SKILL.md)
- [update-skills](./plugin/skills/update-skills/SKILL.md)

## Personal

- [chouge-git](./plugin/skills/chouge-git/SKILL.md)

## Sakura Cloud

- [sakura-cloud-eventbus](./plugin/skills/sakura-cloud-eventbus/SKILL.md)
- [sakura-cloud-webaccel](./plugin/skills/sakura-cloud-webaccel/SKILL.md)
- [sakura-cloud-workflows](./plugin/skills/sakura-cloud-workflows/SKILL.md)

## Writing

- [chouge-changelog](./plugin/skills/chouge-changelog/SKILL.md)
- [chouge-writing](./plugin/skills/chouge-writing/SKILL.md)

## 配布と移行

`plugin/`が正本で、`.agents/plugins/marketplace.json`が補完pluginだけを公開します。
旧15スキルのSKILL.mdは配布treeから除去し、旧方式はGit上の導入済みbaselineで復旧します。
同名の旧tddや旧implementを残したまま無視する構成にはしません。

[固定版と分類](./pstack.lock.json)、[移行と受入手順](./docs/pstack-migration.md)を参照してください。
marketplace登録、第三者codeの実行、hook信頼、global切替、既存自動化の変更は別の承認対象です。
cacheを編集せず、通常のAGENTSとskill検出を使います。

APMの参照は `nananaman/skills/plugin/skills/<name>#<full-sha>` または正本へのpathを使います。
pstackと補完13件はdotfilesのAPM manifestで管理します。旧汎用依存はmanifestから除き、通常のAPM同期で残存配置を照合します。
旧native登録の無効化と個別skill設定の整理は初回切替で行い、旧パスの互換symlinkは追加しません。

## 評価と保管

[skill-workbench](./plugin/skills/skill-workbench/SKILL.md)は本人管理の補完規約を評価する明示呼出しの補助です。
旧maintenanceのrenderer・証拠索引・readerは [tools/skill-maintenance](./tools/skill-maintenance/README.md) に保管し、pluginから配布・自動起動しません。
履歴取得の許可や日次自動化の設定は変更していません。

```sh
python3 scripts/check-skill-inventory.py
python3 -m unittest discover -s tests
```

Apple container、Excalidraw、sandbox診断、Sakura Cloud操作は各skillのOS・CLI・認証・操作権限条件に従います。
モデル実行・実サービス接続・公開を伴わない検査と、それらのRuntime確認は区別します。
秘密、実務履歴、非公開stateはGitへ保存しません。
