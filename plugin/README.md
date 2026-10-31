# nananaman skills

日本語の文書作成、Gitやテストの個人規約、agent skillの作成・評価、サービス操作のためのskillsです。
各skillの用途と必要条件に従って、利用するものを選びます。
配布packageは `nananaman-skills` version `0.3.0` です。

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

## 配布

このdirectoryが配布正本です。manifestは `plugin.json` で直接管理します。
各skillは用途と必要条件に従って単独で利用でき、組合せや導入方法は利用環境で決めます。
APMでは `nananaman/skills/plugin/skills/<name>#<full-sha>` またはローカル正本へのpathを使います。
repository全体の検証と非配布toolsは [root README](../README.md) を参照してください。
