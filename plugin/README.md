# nananaman skills

日本語の文書作成、Gitやテストの個人規約、agent skillの作成・評価、サービス操作のためのskillsです。
各skillの用途と必要条件に従って、利用するものを選びます。
配布packageは `nananaman-skills` version `0.4.0` です。

## Engineering

- [apple-container](./skills/apple-container/SKILL.md)
- [excalidraw](./skills/excalidraw/SKILL.md)
- [no-comments](./skills/no-comments/SKILL.md)
- [nono-sandbox-maintenance](./skills/nono-sandbox-maintenance/SKILL.md)
- [test-writing-style](./skills/test-writing-style/SKILL.md)

`no-comments`は実装・修正・レビュー時に使い、テストも含めて命名・構造・型・振る舞いの検証で意図と制約を表します。
上流の [no-comments](https://github.com/cursor/plugins/blob/e1cc03121a0e71129a4fb730d7c5528a0a3e43c8/pstack/skills/no-comments/SKILL.md) と [comment-sicko](https://github.com/cursor/plugins/blob/e1cc03121a0e71129a4fb730d7c5528a0a3e43c8/pstack/agents/comment-sicko.md) の方針を参考に、このpackageで単独利用できる形にしました。
コメントの削除前に意味と制約を設計へ移し、法的表示・機械向け指示・公開契約を維持します。特定runtimeのagentや設計skillには依存しません。

## Meta

- [create-verification-skill](./skills/create-verification-skill/SKILL.md)
- [apm-usage](./skills/apm-usage/SKILL.md)
- [skill-maintenance](./skills/skill-maintenance/SKILL.md)
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

PRDとDesign Docのテンプレートと使い方は [chouge-writing](./skills/chouge-writing/references/doctypes/prd-and-design-doc.md) に収録しています。

## 配布

このdirectoryが配布正本です。manifestは `plugin.json` で直接管理します。
各skillは用途と必要条件に従って単独で利用でき、組合せや導入方法は利用環境で決めます。
APMでは `nananaman/skills/plugin/skills/<name>#<full-sha>` またはローカル正本へのpathを使います。
repository全体の検証と非配布toolsは [root README](../README.md) を参照してください。
