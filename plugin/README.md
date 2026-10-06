# nananaman skills plugin

日本語の開発・文書作成・レビュー・スキル保守・Git運用・さくらのクラウド手順を含む skills-only plugin です。`plugin/` 自体を正本とし、全skillと付属resourceを `skills/<name>/` に置きます。MCP・app接続・hooksは同梱しません。installだけではCLIやサービスへのアクセス権は追加されません。

## 全27 skills

| 分類 | skills |
| --- | --- |
| Engineering (15) | [apple-container](./skills/apple-container/SKILL.md), [create-plan](./skills/create-plan/SKILL.md), [create-pr](./skills/create-pr/SKILL.md), [draft-design-doc](./skills/draft-design-doc/SKILL.md), [draft-prd](./skills/draft-prd/SKILL.md), [implement](./skills/implement/SKILL.md), [nono-sandbox-maintenance](./skills/nono-sandbox-maintenance/SKILL.md), [polish-design-doc](./skills/polish-design-doc/SKILL.md), [polish-prd](./skills/polish-prd/SKILL.md), [prototype](./skills/prototype/SKILL.md), [review-diff-code](./skills/review-diff-code/SKILL.md), [review-plan](./skills/review-plan/SKILL.md), [task-breakdown](./skills/task-breakdown/SKILL.md), [tdd](./skills/tdd/SKILL.md), [test-writing-style](./skills/test-writing-style/SKILL.md) |
| Meta (4) | [apm-usage](./skills/apm-usage/SKILL.md), [skill-maintenance](./skills/skill-maintenance/SKILL.md), [skill-workbench](./skills/skill-workbench/SKILL.md), [update-skills](./skills/update-skills/SKILL.md) |
| Personal (2) | [chouge-changelog](./skills/chouge-changelog/SKILL.md), [chouge-git](./skills/chouge-git/SKILL.md) |
| Productivity (2) | [grilling](./skills/grilling/SKILL.md), [handoff](./skills/handoff/SKILL.md) |
| Sakura Cloud (3) | [sakura-cloud-eventbus](./skills/sakura-cloud-eventbus/SKILL.md), [sakura-cloud-webaccel](./skills/sakura-cloud-webaccel/SKILL.md), [sakura-cloud-workflows](./skills/sakura-cloud-workflows/SKILL.md) |
| Writing (1) | [chouge-writing](./skills/chouge-writing/SKILL.md) |

## ローカル導入と通常の検出

source checkoutには、repo rootの `.agents/plugins/marketplace.json` があり、その `source.path` は `./plugin` を指します。buildは不要です。導入を決めた利用者はrepo rootで実行します。

```sh
codex plugin marketplace add .
codex plugin add nananaman-skills@nananaman-skills-local
```

対応desktop appではPlugins Directoryからmarketplaceを選んでinstallする経路もあります。導入後は新しい会話のskill一覧、descriptionによる選択、clientの `$skill` / `@plugin` 等を使います。Codexの検出名は `nananaman-skills:<skill>` です。作業対象のAGENTS.mdは通常の検出に任せ、毎回手動のSKILL読取リストを追加する必要はありません。

Git URL、ref、スパースパスをGUIで入力する場合は、[GUIでGit marketplaceを追加する](../README.md#guiでgit-marketplaceを追加する)を参照してください。
`plugins/codex` での追加成功報告と現行mainの配置を区別して記載しています。

APMでも同じ正本を個別に参照できます。旧カテゴリパスは移動するため、manifestを変更してから、許可されたscopeでinstallしてください。全27件のpluginと既存APM展開を同時に有効にすると、同じworkflowが二重に提示されることがあります。既存展開を勝手に消さず、利用者が経路を選んでください。

```yaml
dependencies:
  apm:
    - path: ~/ghq/github.com/nananaman/skills/plugin/skills/implement
    - nananaman/skills/plugin/skills/skill-maintenance#<full-sha>
```

GitHub参照では新パスが存在するcommitのfull SHAを使います。古いSHAのままパスだけ変更しません。ローカルmarketplace・公開GitHub・ChatGPT cloudの導入状態は別です。他端末やcloud accountへ自動同期されたとは扱いません。

## ZIP配布

source checkoutのrepo rootで、commit済みの正本だけをそのまま固めます。別配置へのコピーやskill生成処理は不要です。

```sh
git archive --format=zip --prefix=nananaman-skills/ HEAD:plugin \
  > /tmp/nananaman-skills-0.1.0.zip
```

ZIPは一つのpluginフォルダを含みます。作成前に全件inventory・リンク・resource・秘密を検査します。`git archive` は未追跡のstate・キャッシュ・credentialsを収録しませんが、追跡済みファイルの公開可否は別途確認します。

ZIPだけを受領した場合は再build不要です。空のディレクトリへ展開し、そのディレクトリに `.agents/plugins/marketplace.json` を次の内容で作成して、展開先を `codex plugin marketplace add <展開先>` で追加します。ZIP自体は単一pluginであり、marketplace catalogは含みません。

```json
{
  "name": "nananaman-skills-local",
  "plugins": [{
    "name": "nananaman-skills",
    "source": {"source": "local", "path": "./nananaman-skills"},
    "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
    "category": "Productivity"
  }]
}
```

同じmarketplace名を既に利用している場合は重複追加せず、sourceを確認します。

## 対応条件

| 範囲 | 必要な環境・制約 |
| --- | --- |
| 文書・計画・レビュー | 対象資料・編集先・必要なagent / subagent / toolが利用可能な環境。文章作成だけならローカルCLIが不要な経路もあります |
| Git / PR | Git、必要時にGitHub CLI、利用者本人の認証・操作権限 |
| APM / update-skills | APM・Git・manifest・install scope。例の `~/ghq/...` は本人の実際の配置へ読み替えます |
| skill-workbench / skill-maintenance | Python 3.11+。モデル実行・取得には対応Codex CLIと許可済みcaller設定・入力・repo外の私的stateが必要です |
| skill-maintenance のCodex取得 | 現行readerはMacローカルと登録済み情報scopeが必要です。`--repo`に改善対象repoを明示し、state/outputを対象repo・reader配布ツリー・reader自身のGit checkout外へ置きます。Work intakeにはhostの列挙・send/read・Mac委譲能力が別途必要です |
| apple-container | Apple silicon Mac、macOSと `container` CLIの対応版。referenceの前提を確認します |
| nono-sandbox-maintenance | nonoと対象sandbox / profile。macOS Seatbelt等のOS固有経路は該当OSでのみ利用します |
| prototype | artifactに応じたbuild / UI / browser等のtool。macOS Flutterの例は他OSへそのまま適用しません |
| Sakura Cloud | 対象サービス・zone・CLI / HTTP tool・credentialと操作権限。API例にはcredentialを含めません |

Windows / cloudで全workflowを実行した互換性試験は行っていません。配布・検出と、workflow実行可能性は分けて確認します。clientの一覧容量制限もあるため、収録全件とmodelに最初から提示される全件は同義ではありません。

## 移行と日次運用

正本パスは旧 `engineering/` 等から `plugin/skills/<name>/` へ変わります。旧パスのコピー・symlinkは用意しません。APM利用者はmanifestとローカル正本を同じ配置へ揃えた後にinstallします。運用checkoutや実manifestの同期・installは別の許可された操作です。

日次callerが旧パスのscriptを直呼び出ししている場合は、新パスとreaderの `--repo` を更新する必要があります。skill名だけで呼び出す場合も、導入済みの正本・展開先が更新されたか確認します。新readerは対象repoを再開bindingへ含めるため、旧progressとbindingが一致しなければ停止して照合します。自動削除・再取得・古い実行契約への無断適用はしません。Mac専用条件や取得権限は引き継がれたと推測しません。

## 公開内容

公開の `nananaman` / `chouge` 表記と個人用作業規約も含みます。秘密・実組織名・環境固有の実絶対path・実務ログ・stateは収録しません。`/Users/` の文字列は履歴最小化コードの正規表現であり、実端末pathではありません。example.com / example.invalidと匿名JSONは合成例です。

公開directoryでは、作者がPlatformの所有org/projectと公開identityを確定し、ZIP upload・検査解消・review・承認後のpublishを行います。skills-only packageは対応していますが、このZIPのportal検査・審査は未実施です。workspace導入・一般向けinstall linkも別途確認します。merge・実アカウント導入・公開申請はこのPRに含みません。

仕様の参考（2026-10-06確認）:

- [公式package guide](https://developers.openai.com/plugins/build/plugins)
- [skill検出・呼び出し](https://learn.chatgpt.com/docs/build-skills)
- [ChatGPTでのplugin利用](https://learn.chatgpt.com/docs/build-plugins)
- [ZIP検査・審査・公開](https://developers.openai.com/plugins/deploy/submission)
