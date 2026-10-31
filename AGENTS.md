# AGENTS.md

このrepositoryはnananamanのpstack補完規約と専門skillの正本です。

## 正本と配置

- 配布正本は `plugin/skills/<name>/SKILL.md` と配下の資材。frontmatter名とdirectory名を揃える。
- 汎用の計画・実装・設計・TDD・レビュー・PR・振り返りはpstackを使い、独立した旧入口を再追加しない。
- 日本語規約、repo固有の要求、許可境界を優先する。必要な契約コメントと検証を削らない。
- `tools/skill-maintenance/`は非配布の保管用tool。履歴や日次振り返りを自動起動しない。
- 秘密、私的state、実務履歴、認証情報はrepo外に保管する。

## 更新と配布

1. 正本を編集し、追加・削除・renameではrootとpluginのREADMEを同期する。
2. pstackのauthoring・レビュー手順を使い、補完規約の評価が必要なら明示的にskill-workbenchへ渡す。
3. inventory、リンク、資材、公開内容、対応条件、固定依存を確認する。
4. actionable findingがなく、ユーザーが明示依頼した場合だけcommit・pushする。
5. APM manifest更新・install・hook信頼・global切替は、今回許可された操作だけを行う。

`plugin/plugin.json`と`.agents/plugins/marketplace.json`を直接管理し、生成copy工程は作らない。
配布版を戻す際は移行手順のbaseline commitを使い、旧skillの互換copyやsymlinkを追加しない。
通常のAGENTS・skill検出を使い、起動promptに手動のSKILL読取リストを追加しない。

## 検証

```sh
python3 scripts/check-skill-inventory.py
python3 -m unittest discover -s tests
```

第三者pstackのinstall・実行が承認待ちなら、そのRuntime確認だけを保留し、安全な正本編集と静的検査は続ける。
