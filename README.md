# nananaman skills

日本語の文書作成、Gitやテストの個人規約、agent skillの作成・評価、サービス操作のためのskillsです。
各skillの用途と必要条件に従って、利用するものを選びます。
配布packageは `nananaman-skills` version `0.3.0` です。

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

## 配布と利用

`plugin/`がインストール可能な正本で、`.agents/plugins/marketplace.json`が配布情報を持ちます。
APMでは `nananaman/skills/plugin/skills/<name>#<full-sha>` またはローカル正本へのpathで各skillを参照できます。
導入先の組合せや同期taskは、その環境の設定で管理します。
各skillのOS・CLI・認証・操作権限の条件を確認し、installや実環境への反映は依頼された範囲だけ行います。

## 検証と保管用tools

```sh
python3 scripts/check-skill-inventory.py
python3 -m unittest discover -s tests
```

[skill-workbench](./plugin/skills/skill-workbench/SKILL.md)はskill・AGENTS.md・tool指示の作成、改善、レビュー、比較評価を扱います。
配布対象外のrenderer・証拠索引・readerは [tools/skill-maintenance](./tools/skill-maintenance/README.md) に保管しています。
秘密、実務履歴、非公開stateはGitへ保存しません。
