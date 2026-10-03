# 0.160.0 の限定対応

この対応はCLI `0.159.3`の生バイトproxyを使って、既存app-server `0.160.0`へ接続し、`initialize`と`thread/read includeTurns:false`だけを行う。新しいCLIの実行・インストールは不要。サーバー版はuserAgentの先頭originator/build-versionから完全一致で選び、OSやclientの版番号をCodex版として使わない。未知版・suffix付き版は停止する。

## 公式契約の照合

OpenAIの公開repoの`rust-v0.159.3`と`rust-v0.160.0`から次を取得し、同じGit blobであることを確認した。最新版mainで代用しない。

| schema（0.160.0へのリンク） | 両tagのGit blob SHA | 確認内容 |
| --- | --- | --- |
| [InitializeParams](https://github.com/openai/codex/blob/rust-v0.160.0/codex-rs/app-server-protocol/schema/json/v1/InitializeParams.json) | `750dddeaf5f551257110120effed655141eab5bf` | clientInfoのname/version、capabilities.experimentalApi |
| [InitializeResponse](https://github.com/openai/codex/blob/rust-v0.160.0/codex-rs/app-server-protocol/schema/json/v1/InitializeResponse.json) | `1de65f82f4df9fa810fbda3ff199eca49430a29f` | userAgent/codexHome/platformFamily/platformOs |
| [ThreadReadParams](https://github.com/openai/codex/blob/rust-v0.160.0/codex-rs/app-server-protocol/schema/json/v2/ThreadReadParams.json) | `920e6c346d6b6fca1773e7ea4b68c69dee46dec1` | 必須threadId、任意boolean includeTurns |
| [ThreadReadResponse](https://github.com/openai/codex/blob/rust-v0.160.0/codex-rs/app-server-protocol/schema/json/v2/ThreadReadResponse.json) | `9f11927d728a0b81a65ddcac85b6ac468c552611` | 必須thread object、必須metadataとThreadStatus |

installed CLI `0.159.3`の生成schemaでもinitializeの両schemaとThreadReadParamsが一致した。ThreadReadResponseは公開tagとの比較で、Threadの任意property `canAcceptDirectInput / daybreakEnabled / environments / extra`が追加されていた。必須property・thread/read要求・runtime statusの契約は一致した。追加propertyを新しい権限やAPI対応の証拠にしない。

要求はIDと`includeTurns:false`だけに制限する。応答は必須metadataの存在、使用するfieldの型、返却ID一致、絶対cwd、turns空配列、runtime status、active時の既知activeFlagsを検査する。その他の任意metadataは使わない。`Thread.cliVersion`は記録作成時のCLI版であり、接続サーバー版の判定に使わない。

[公式app-server文書](https://developers.openai.com/codex/app-server/)のthread/readは保存記録をresumeせず読み、正常応答の`status.type:notLoaded`も許容する。RPC errorの`thread not loaded`とは区別する。

## userAgentの解析修正

[公式get_codex_user_agent](https://github.com/openai/codex/blob/rust-v0.160.0/codex-rs/login/src/auth/default_client.rs)は、`originator/build_version (OS version; architecture) client_user_agent`に任意client suffixを付ける。build_versionはサーバーのCARGO_PKG_VERSIONであり、originator名は固定のcodex_cli_rsとは限らない。従来のCodex名限定検索ではdesktop originatorを認識できず、desktop originatorの0.160.0も版未検証と判定される。先頭の正式な生成形式を検査する解析へ修正した。originator内の空白も許容し、制御文字・曖昧な区切り・未知版は停止する。後続clientの版やsuffix中のCodex文字列は版の選択に使わない。

fixtureのuserAgentは限定試行の観測値と同じ区切りを持ち、originator・OS・architecture・client名とその版を置換したもの。Codex build_version以外は判断に使わず、実会話・thread ID・ホームを含めない。修正後の限定thread/read試行はRPC notLoadedで終了し、metadataと本文の取得は成功していない。

## 対応範囲と検証

[合成metadata fixture](../examples/codex-0160-metadata.json)とテストで、0.160.0のinitializeと正常notLoaded metadata、返却ID・型・時刻・cwd・turn本文混入の拒否、未検証methodの送信前拒否を確認する。これは実データの取得成功を表さない。

0.160.0では`thread/list / thread/turns/list / thread/items/list`や`includeTurns:true`を許可しない。したがって日次exportの0.160.0対応は未完了であり、metadata読取の成功から履歴取得成功を推論しない。unknown versionへのfallback、resume、daemon更新・再起動、設定変更は行わない。限定実データ試行は、承認済みID一件の成功・RPC notLoaded・権限拒否・具体的なschema不一致のいずれかで終了する。
