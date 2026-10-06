# macOS の子プロセス

このbranchは、親commandが内部でFoundation `Process`、shell、absolute pathなどから子processを起動して失敗した場合だけ使う。

1. 公式source、実行ログ、実機helpのいずれかで子executableとargvを確認する。
2. PATH shimで制御できる呼出しか、absolute pathのdirect execかを分ける。
3. `command -v`の結果が`$NONO_TOOL_SANDBOX_SHIM_DIR`配下なら、それを実体として追跡せず、source profileまたは`nono profile show`からcommand policyの`executable`を確認する。
4. sandbox外の`command -v`、`realpath`、`file`、起動scriptの内容から、command policyの`executable`がwrapperか実binaryかを確認する。Nix packageでは`bin/<command>`が同じdirectoryの`.<command>-wrapped`などを起動する場合があるため、名前を推測せず生成物を調べる。
5. wrapperが必須environmentを設定していなければ実binaryをpinし、設定しているなら`environment.set_vars`で再現できるか確認する。nonoが生成する標準PATH shimで到達できるcommandに同名wrapperを追加せず、追加が必要ならPATH順序の再現とpackage集合内の`bin/<command>`衝突がないことを先に確認する。
6. package managerなどのshimがversioned実体へ解決される場合は、versioned pathをprofileへ直書きせず、pinした実体から呼出設定とsandbox許可を同時に生成できるか確認する。
7. `allow_direct_exec_bypass` はpinしたpolicy-controlled command本体のdirect invocation用であり、親commandが起動する任意の子executableを許可するfieldではない。子processの許可へ流用しない。
8. `unsafe_macos_seatbelt_rules` が必要なら、対象commandのchild sandbox内でexact executableだけを許可する。directory prefixや任意process execへ広げない。
9. OS tool自身がsandbox実行を拒否する場合は権限追加を止め、sandbox外の人間向け診断へ分離する。

raw Seatbelt ruleはvalidator warningを残す設計上の例外である。警告を消すためにscopeを広げない。

完了条件: child execの経路、pinした実体、追加rule、またはsandbox内で対応不能な理由が明示された。
