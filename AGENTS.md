# AGENTS.md

このrepositoryはnananamanの個人用agent skillsのsource of truthです。

## 正本と配置

- 配布正本は `plugin/skills/<name>/SKILL.md` と配下の資材。frontmatter名とdirectory名を揃える。
- 各skillは用途・必要条件・完了条件を自分の責務の範囲で記述する。特定の開発フロー、導入先の設定や移行方針をpackage全体の前提にしない。
- 用途別の分類はrootとpluginのREADMEで示し、旧カテゴリパスのcopyや互換symlinkを追加しない。
- 日本語で書いてよい。provider・product名は必要ならskill名へ含める。
- 秘密、私的state、実務履歴、認証情報はrepo外に保管する。

## 更新と配布

1. 正本を編集し、追加・削除・renameではrootとpluginのREADMEを同期する。
2. `skill-workbench`で必要な差分レビューを行う。実行コードは必要な検証と実装者とは独立した差分レビューも行う。
3. inventory、リンク、資材、公開内容、対応条件を確認する。配布版ではmanifest versionと全件一覧を照合する。
4. actionable findingがなく、ユーザーが明示依頼した場合だけcommit・pushする。
5. APM manifest更新・install・実環境への反映は、その操作が依頼された場合だけ行う。pathまたはfull SHA方式と、参照先のpath・commitの対応を確認する。

`plugin/plugin.json`と`.agents/plugins/marketplace.json`を直接管理し、生成copy工程は作らない。
APMからは `nananaman/skills/plugin/skills/<name>#<full-sha>` でも参照できる。
ZIPは必要な場合だけ追跡済みpluginをgit archiveし、Git管理外へ保存する。
marketplace登録、実アカウントへの導入、公開directoryへの公開はそれぞれ別操作とする。
通常のAGENTS・skill検出を使い、起動promptに手動のSKILL読取リストを追加しない。

## 検証

```sh
python3 scripts/check-skill-inventory.py
python3 -m unittest discover -s tests
```
