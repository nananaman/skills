# AGENTS.md

このリポジトリは nananaman の個人用 agent skills の source of truth です。

## 正本と配置

- `plugin/` がインストール可能なプラグインの正本。
- 全 skill は `plugin/skills/<name>/SKILL.md` と、その配下の references・scripts・assets 等に置く。frontmatter の `name:` とディレクトリ名を一致させる。
- 日本語で書いてよい。provider・product の名前は `sakura-cloud-eventbus` のように skill 名へ含める。
- 用途別の分類は README の Engineering / Meta / Personal / Productivity / Sakura Cloud / Writing の一覧で示す。旧カテゴリパスにコピーや互換 symlink を追加しない。
- 各 skill は APM から `nananaman/skills/plugin/skills/<name>#<full-sha>` でも参照できる。
- セキュリティ上公開できない内容はこのリポジトリに置かない。私的な state・実務記録・認証情報はrepo外に置く。

## 更新手順

1. 正本の skill・resource を編集する。
2. 追加・削除・rename の場合は root と plugin の README の一覧・導線も更新する。
3. `skill-workbench` で変更に必要な差分レビューを行う。実行コードは `implement` の検証・独立レビューも行う。
4. actionable finding がなく、ユーザーが明示依頼した場合だけ commit / push する。
5. dotfiles の `home/.apm/apm.yml` の参照更新・APM install はユーザーが依頼した場合だけ行う。path / full SHA の方式を保ち、配置変更はpathと対応するcommitを照合する。

## 配布

- `plugin/plugin.json` と `.agents/plugins/marketplace.json` を直接管理する。plugin を生成するコピー工程は設けない。
- ZIP が必要なときだけ、追跡済みの plugin 正本を `git archive` で固める。ZIP はGit管理外へ保存する。
- 配布版の更新時はmanifest versionと全件inventory・resource・リンク・公開内容・対応条件を確認する。
- marketplace追加、実アカウントの導入、cloud / 公開directoryへの公開は別操作。commit・push・ZIP作成を導入成功と扱わない。
- 通常のAGENTS/skill検出を使い、起動promptへ手動のSKILL読取リストを追加しない。

## 検証

```sh
python3 scripts/check-skill-inventory.py
python3 -m unittest discover -s tests
python3 -m unittest discover -s plugin/skills/review-diff-code/tests
```
