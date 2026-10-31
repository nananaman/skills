# pstackをAPMで標準にする移行

本人packageは補完13件の0.3.0とし、旧汎用15件を配布treeから除く。
pstackの互換確認版は0.9.114 / 5851c89613e2ddc3a6b7f4af02a42363b30ef8d3で、分類は [pstack.lock.json](../pstack.lock.json) に記録する。
実導入の正本はdotfilesの `home/.apm/apm.yml`。pstackのplugin packageと本人skillを同じAPMで管理する。

## 配布と入口

- 旧24件を固定する互換viewや、配置を残したまま隠す恒久routerは作らない。
- APMの旧汎用14依存を除く。prototypeはAPMに未登録だったため、配布treeでの廃止は計15件となる。
- 現在の補完10件とSakura Cloud3件を本人正本pathで参照し、全13件を維持する。
- 通常開発はpoteto-mode、学びは明示reflectの提案まで。日本語、repo規約、外部操作の許可境界、必要な契約コメントと検証を保持する。
- maintenance資材は非配布toolsに保管し、日次自動化の継続・停止・移行は別途承認する。

## 共通指示と設定

共通の作業指針はdotfiles `home/.agents/AGENTS.md`、モデル表は実行環境の `pstack-models.md` とする。
共有指示にクライアント分岐、旧implement呼出し、移行事情、特定providerのモデルIDを置かない。
モデル・effortは明示し、session履歴の自動読取に依存しない。通常は同時2担当までとする。

## 検証と切替

APM0.29.0はpluginのskill・agent・hook定義を展開する。native plugin登録そのものは開発フローの必須条件ではない。
APMのfull installで除去済み依存の配置を照合し、所有不明・手編集fileの残存を確認する。
別登録の旧native0.2.0の無効化と、既存のAPM skill非表示設定の整理は初回切替に必要である。
資材を壊さず、元ユーザー変更と無関係なvendorを保持する。必要なら旧tddの除去とpstack追加を2回のAPM同期に分ける。

固定source671 fileを照合し、隔離APMで67 skills・4 agents・SessionStart設定の展開を確認した。
元のhookはCLAUDE_PLUGIN_ROOT未定義で失敗し、root明示では各5秒以内の比較で固定contextを出力した。ネットワーク・モデル・認証情報は使っていない。
dotfilesの `mise run apm-sync` はfull install後に、小さな互換処理でpstackの起動コマンドとAPM sidecarへrootを補う。配布script・lock・他hook・信頼設定は変更しない。
固定sourceのhashと現存コマンドが違う場合は補正を止める。pstack/APM更新時は互換処理を再評価し、直接installした場合も補正前にsessionを開始しない。
pstack:<name>参照は、共通指示に従い同じ配布元の検出済みbare skill/agent名へ対応付ける。Claudeのpstack:poteto-agentを含むモデル上の実呼出しは未検証である。
通常環境の新hook信頼・実行、モデル受入、切替とmergeは未実施で、個別の許可範囲に従う。

## 復旧と配布

baselineは0.2.0 / d25aec07e3fd2695165e274330afa7d183ba3e6a。privateな設定・元値・link・APM所有記録を保存し、変更した範囲だけを復旧する。
pstackを撤去するときは依存削除前にAPM uninstallでmerged hookも除く。full installだけではhookが残る場合がある。
旧native cacheとsourceは受入まで残す。GitHub main、無関係な設定、Orca/textlint、他の自動化を一括で戻さない。
commit/push・PR更新・merge・実導入は、それぞれ許可された操作だけを行う。
