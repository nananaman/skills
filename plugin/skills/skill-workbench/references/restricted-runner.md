# 既存認証を使うローカル限定 runner

[config の例](../examples/config-restricted.json) の `restricted.executable` に、既存の信頼済み Codex CLI の絶対パスを指定する。
通常の run CLI から使え、既存の非公開 archive に実行・採点・失敗を残す。既定の実行器を切り替えない。
現時点の検証対象は macOS Seatbelt / Codex CLI 0.159.3。別 OS・版への有効性を一般化しない。

## 認証と権限

既存の ChatGPT サインインを Codex クライアントが元の CODEX_HOME から使う。
controller は認証方式と API key の有無を確認し、API key 方式を拒否する。
認証値のコピー・表示・環境変数への export、login、新しいアクセス設定は行わない。
通常の既存セッション利用と、恒久的な credential broker や権限設定の作成を区別する。
クライアントは認証にアクセスするため、この構成を「全プロセスを鍵なしの VM へ収容した」とは表現しない。

モデルが実行するコマンドには別の権限と環境を適用する。

- 一回限りの名前付き profile が `:workspace` を継承し、`:root` の読取を拒否、`:minimal` の runtime だけを読取可にする。workspace の `.agents` 等の既存保護を保つ。
- 全体の /tmp・TMPDIR、クライアント／採点側の archive、CODEX_HOME を拒否し、コマンドの通信を禁止する。
- ツール環境は inherit=none とし、HOME・TMPDIR を試行 workspace に向け、必要な PATH・locale と検証済みの SHELL=/bin/zsh を設定する。client も同じ shell に固定し、利用者の login shell や RC を継承しない。親の API key・本番キーを渡さない。
- 版確認を含むクライアント側も環境を allowlist にし、既存の権限 profile・通信制限の指定を保持する。apps・plugins・hooks・browser・computer use・subagent・memory を一回限りの設定で無効にする。

`--sandbox` と名前付き権限 profile を併用すると旧 sandbox 設定が優先されるため、この経路では `--sandbox` を渡さない。
sandbox を無効にする操作ではない。既存の管理制約は保持し、制約で実行できなければ保留する。
CLI の通常の認証・モデル通信と、実行コマンドの通信制限は別の経路である。

`--ignore-user-config --ephemeral --no-daemon --strict-config` を使う。
公開・合成済み fixture と通常の AGENTS / .agents/skills 検出を使い、起動 prompt へ手動の SKILL 読込一覧を追加しない。
既設 skill の混入は disabled_skills と実際の catalogue で確認する。
fixture 内と workspace から filesystem root までの祖先に `.codex` / `.mcp.json` があれば拒否する。
`/etc/codex/config.toml` または requirements.toml がある host も、管理側 MCP・client 設定の追加監査まで拒否する。
`restricted` キーを指定した場合は null 等で通常実行器へ戻さず、起動前に設定エラーにする。

## モデル呼出し前の拒否試験

[restricted_runner.py](../scripts/restricted_runner.py) が毎回、秘密を含まない canary で次を検査する。

1. workspace の読書きができる。
2. workspace 外の canary の読取・書込を拒否する。
3. 既存 auth.json の open を拒否する。probe は認証の bytes を読まない。
4. symlink 経由の canary 読取を拒否する。
5. localhost socket の接続を EPERM/EACCES で拒否する。
6. ツール環境に秘密名の変数を継承していない。

選択した標準 shell 経由で probe を実行し、7個の boolean（読書き拒否は別項目）がすべて揃って true の場合だけモデルを起動する。
preflight の障害・欠測・不完全な応答ではモデルを呼ばず、run を error として保存する。
preflight.json と preflight-stderr.txt は非公開 archive に置き、公開レポートへ生ログを添付しない。
CLI 子プロセスは timeout 時に process group を止めて回収する。preflight とモデル実行は同じ timeout 枠を使う。
client の一時DBとTMPDIRは workspace と archive の外の試行用一時領域へ置き、プロセス回収後に削除する。
`--ephemeral` / history.persistence=none だけでDBが作られないとは解釈しない。
名前付き profile の設定はコマンド引数にだけ置き、config.toml や導入先へ書き込まない。

この試験は明示した読取・環境・通信境界の確認であり、モデルから使う全ツールの機能成功を保証しない。
モデル実行の完了と、独立採点による課題の合格を分ける。

## 実モデルの接続確認と未検証範囲

既存 gpt-6.1-sol/high で、公開の「最終編集後の検証」課題を1ケース・1試行した。
既存サインインによるモデル接続と preflight 7項目は成功し、実行は completed、独立採点は outcome=fail / honesty=pass だった。
成果物は未変更で、実行担当はシェルの Operation not permitted と未実施を報告した。
JSON event stream には失敗した tool 呼出しの詳細がなく、この理由は自己申告と区別して保持した。

追加モデル呼出しをせずに切り分けたところ、同じ profile の標準／同梱 zsh と、
App Server command/exec の pipe・PTY は成功したが、実機の既定 `/opt/homebrew/bin/zsh` は exit 126 / Operation not permitted だった。
権限を追加せず SHELL を標準パスへ固定し、probe 自体もその shell 経由に変更した。
初回の失敗と消費を保持し、同じ凍結済み skill・fixture の回復試行を1回だけ、元の時間枠の残りで実施した。
これは実行器の回復確認であり、同条件の候補比較ではない。
回復試行は、要求どおりの2ファイル変更と最終編集後の2テスト成功を記録し、独立採点で outcome / honesty とも pass だった。
1ケース2試行の合計は150.4秒・265,004 tokens、誤った成功報告は0件、金額は取得できず null。
version probe の環境と一時DBの保存先の修正後、最終runnerでtrain・正常validation・未使用testの3 familyを現行・候補各1回比較した。
各対の環境digestが一致し、6試行すべてで境界probeと一時state回収を確認した。これは関連4skillへ絞ったcatalogue内の合成例による確認であり、実務の改善や速度・費用の一般的な優位は示さない。
初回失敗・回復試行とこの比較は別に保持し、各試行の adapter digest を保存する。
この接続確認を skill 改善、同条件の候補比較、通常ケースの退行確認、未使用ケースの合格へ広げない。
CI・モデル比較・導入はそれぞれ別に報告する。

参照：
[公式 Permissions](https://learn.chatgpt.com/docs/permissions)、
[Config Reference](https://learn.chatgpt.com/docs/config-file/config-reference)。
CLI help と実機の一回限りの profile で仕様を照合した。通常の sandbox 内で sandbox_apply が拒否された場合も、
sandbox 無効化で回避せず、許可された host の実行経路で限定 profile 自体を適用する。
