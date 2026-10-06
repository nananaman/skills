# nananaman skills plugin

nananaman/skills の全スキルをまとめた skills-only プラグインです。日本語の開発・文書作成・レビュー・スキル保守・Git 運用・さくらのクラウド手順を含みます。MCP server、app 接続、hooks は同梱しません。インストールだけでは CLI、端末、サービスへのアクセス権は追加されません。

## 正本とパッケージ

用途別カテゴリの `SKILL.md` と付属ファイルが正本です。APM の既存 path / SHA 参照は維持します。source repository の `plugin/` は manifest と配布説明の入力です。生成済みフォルダの root にあるこの README は配布説明であり、そのフォルダはインストール可能なプラグインです。生成済み ZIP の受領者は再ビルド不要です。

source checkout の repository root で Python 3.11+ と Git を使って生成します。外部 Python dependency は不要です。

```sh
python3 scripts/check-skill-inventory.py
python3 scripts/build-plugin.py
```

出力は `_build/plugins/` に作成します。

- `nananaman-skills/`: root `plugin.json` と `skills/<name>/SKILL.md` を持つプラグイン。
- `nananaman-skills-0.1.0.zip`: プラグインフォルダを一つ含む配布用 ZIP。
- `.agents/plugins/marketplace.json`: 同じ出力内のプラグインを指すローカル marketplace。

再生成は新しい空の出力先を `--output` で指定します。既存の出力は上書き・削除しません。生成物を正本として編集・commit しません。配布版の変更時は `plugin/plugin.json` の version も更新します。

builder は Git 追跡済みの全 `SKILL.md` を列挙し、各 skill 配下の追跡済みファイルだけを同梱します。未追跡 skill、欠落ファイル、symlink、重複名、パッケージ外への相対 Markdown link はエラーです。各 skill のディレクトリ名を frontmatter の name に揃え、Markdown link を移設先へ変換します。スクリプトとその他の resource はそのまま同梱し、実行権限も保持します。`inventory.json` に全 skills の正本・配布先と各ファイルの SHA-256 を記録します。AGENTS.md、APM manifest、repository の tests、私的状態・生ログは自動では同梱しません。skill 自身に属する追跡済み tests と合成 examples は同梱します。

## 含まれる全 27 skills

| 分類 | skills |
| --- | --- |
| Engineering (15) | apple-container, create-plan, create-pr, draft-design-doc, draft-prd, implement, nono-sandbox-maintenance, polish-design-doc, polish-prd, prototype, review-diff-code, review-plan, task-breakdown, tdd, test-writing-style |
| Meta (4) | apm-usage, skill-maintenance, skill-workbench, update-skills |
| Personal (2) | chouge-changelog, chouge-git |
| Productivity (2) | grilling, handoff |
| Sakura Cloud (3) | sakura-cloud-eventbus, sakura-cloud-webaccel, sakura-cloud-workflows |
| Writing (1) | chouge-writing |

一覧は初版の構成です。以後の全件収録は builder と `inventory.json` で確認します。追加時にパッケージ用 SKILL 正本を複製する必要はありません。

## 導入と通常の検出

生成した marketplace root をローカル client に追加します。次のコマンドは実際の利用者設定を変更するため、導入を決めたときだけ実行します。

```sh
codex plugin marketplace add ./_build/plugins
```

Codex CLI 0.159.3 では、追加後に `codex plugin add nananaman-skills@nananaman-skills-local` でインストールする経路も確認しています。

対応する desktop app の Plugins Directory で `nananaman skills (local build)` を選び、`nananaman skills` をインストールします。導入後は新しい会話でスキル一覧を確認し、通常の description による選択、`$skill` / `@plugin` 等の client の呼び出しを使います。毎回手動で SKILL 読取リストを追加する運用は不要です。AGENTS.md は作業対象 repository の通常の検出に任せます。

既存 APM skills とこのプラグインを同時に有効にすると、同名 skill が二重に提示されることがあります。既存 APM 展開を勝手に消さず、利用する経路を一つ選ぶか、利用者が該当 skill の有効状態を調整してください。

生成済み ZIP だけを受け取った場合は、空のディレクトリへ展開し、`nananaman-skills/` と並ぶ `.agents/plugins/marketplace.json` を次の内容で作成します。そのディレクトリを `codex plugin marketplace add <展開先>` で追加した後、上記の方法で導入します。ZIP 自体は公開 portal 向けの単一プラグインであり、marketplace catalog は含みません。

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

Codex の検出名は `nananaman-skills:<skill>` になります。同じ marketplace 名を既に利用している場合は重複追加せず、元の source と更新先を確認します。

この source repository を GitHub marketplace として追加するだけでは生成処理は走りません。先にローカル build を行い、その出力を使います。GitHub 上の公開 repository、ローカル marketplace、ChatGPT cloud の導入状態は別です。この変更だけで他端末・cloud account への同期やインストールは完了しません。

## 対応条件

| 範囲 | 必要な環境・制約 |
| --- | --- |
| 文書・計画・レビューの指示 | 読取対象、編集先、必要な agent / subagent / tool が利用可能な実行環境。文章作成だけならローカル CLI が不要な経路もあります |
| Git / PR | Git、必要時に GitHub CLI と本人の認証・操作権限。インストールは認証を代行しません |
| APM / update-skills | APM、Git、利用者の manifest と install scope。例示される `~/ghq/...` 等は本人の実際の配置へ読み替えます |
| skill-workbench / skill-maintenance | Python 3.11+。モデル実行・取得には対応 Codex CLI と caller が許可した設定・入力・非公開の state が必要です |
| skill-maintenance の Codex 履歴取得 | 現行 reader は Mac ローカルと登録された情報 scope を要求し、他 OS を拒否します。Work intake は host 側の列挙・send/read・Mac 委譲能力が別途必要です。未対応 source は取得成功と報告しません |
| apple-container | Apple silicon Mac、macOS と `container` CLI の対応版。各 reference の前提を確認します。Windows / Linux / cloud 上の同等実行を保証しません |
| nono-sandbox-maintenance | nono と対象 sandbox / profile。macOS Seatbelt 等の OS 固有経路は該当 OS 上でだけ使います |
| prototype | artifact の種類に応じた build / UI / browser 等のツール。macOS Flutter の例は他 OS にそのまま適用しません |
| Sakura Cloud | caller の対象サービス・zone・CLI / HTTP tool・credential と操作権限。API 例は credential を含まず、接続は利用者側で用意します |

全スキルを Windows / cloud で実行した互換性試験は行っていません。配布・検出の成立と、各 workflow の実行可能性は分けて確認してください。client の skill 一覧の容量制限もあるため、収録全件と model に最初から提示される全件は同義ではありません。

## 初版の検証範囲

2026-10-06、Mac 上の Codex CLI 0.159.3 と隔離した一時設定で、生成 marketplace の追加・一覧・テストインストールから `skills/list` による全 27 件の検出まで確認しました。検出エラーは 0 件でした。実ユーザー設定・アカウントへのインストールは行っていません。

source inventory と package inventory は 27 件で一致し、ZIP と生成フォルダの全ファイル、記録した SHA-256、symlink がないことを確認しました。repository の 245 tests と review helper の 41 tests、secretlint による生成物の秘密検査が通りました。これらは全 workflow の実行、自然な依頼での暗黙選択、desktop UI、Windows / cloud、公開 portal の検査・審査を証明するものではありません。

## 公開内容とライセンス

公開 package にはユーザー名 `nananaman` / `chouge` とその個人の作業規約も含めます。汎用 bundle へ置き換えて個人用 skill を隠す構成にはしません。秘密、実組織名、個人の実絶対 path、実務ログ・状態は収録しません。`/Users/` の文字列は履歴最小化コードの正規表現で使われ、実端末 path を表しません。example.com / example.invalid と匿名化された JSON は合成例です。配布のたびに追跡ファイルと生成物を秘密検査し、内容を確認してください。

`grilling` の第三者由来の表示と MIT License はその skill 内の NOTICE.md / LICENSE に保持します。repository 全体には現時点で共通の LICENSE がありません。全体を MIT 等で再許諾したと主張せず、広く再利用させるライセンスの選択は作者の別判断に残します。

## ChatGPT cloud / 公開 directory への次の手順

新 PR の merge、利用者アカウントへの導入、workspace import、外部 directory 審査申請はこのパッケージ生成には含まれません。

公開 directory では、作者が Platform の所有 organization / project と公開 identity を確定し、ZIP を upload、検査結果を解消して review に提出し、承認後に publish します。skills-only package は対応していますが、この ZIP の portal 検査・審査は未実施です。workspace GitHub import は対象 workspace の管理者設定・対応形式を別途確認します。一般向け install link は directory 公開後に確認します。

仕様・導入経路の参考（2026-10-06 確認）:

- [公式 package guide](https://developers.openai.com/plugins/build/plugins)
- [公式 skill 検出・呼び出し](https://learn.chatgpt.com/docs/build-skills)
- [ChatGPT での plugin 利用](https://learn.chatgpt.com/docs/build-plugins)
- [公開 directory の ZIP・審査・公開](https://developers.openai.com/plugins/deploy/submission)
