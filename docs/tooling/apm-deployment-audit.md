# APM の展開状態を照合する

`scripts/check-apm-deployment.py` は manifest、lock、正本の Git commit、ローカル参照または APM cache、Codex と Claude の展開内容を読み取り専用で照合する。ネットワークアクセス、fetch、install、update、ファイル修正は行わない。Python 3、PyYAML、`--no-lazy-fetch` に対応する Git が必要。依存ライブラリも自動導入しない。

```sh
python3 scripts/check-apm-deployment.py --scope global \
  --source-repo /path/to/skills --commit <full-sha> --json
python3 scripts/check-apm-deployment.py --scope project --root /path/to/project \
  --source-repo /path/to/skills --commit <full-sha>
```

`--commit` の既定値は `--source-repo` の HEAD。固定版を確認するときは、その版の commit を明示する。最新版や remote の HEAD を推測しない。必要な commit や blob がローカル Git にない場合は照合不能になる。Git の [lazy fetch を禁止するオプション](https://git-scm.com/docs/git#Documentation/git.txt---no-lazy-fetch)も明示する。

## 確認する範囲

| 項目 | 確認内容 |
| --- | --- |
| global | `~/.apm/apm.yml` と同じディレクトリの lock。展開先は `~/.agents/skills`、`~/.claude/skills` |
| project | `--root` 直下の manifest と lock、同じ root の `.agents/skills`、`.claude/skills` |
| manifest | ローカル path、または `nananaman/skills/plugin/skills/<name>#<full-sha>`。manifest の論理パスと実体を表示 |
| 正本 | 対象 commit の `plugin/skills/<name>` 全ファイル。ローカル編集も commit と比較 |
| lock | 依存の対応、SHA pin の resolved commit、両展開先と配下ファイルの配置記録、ファイル別 SHA-256 と対象 commit の一致 |
| 展開内容 | 対象 commit に対するファイルの不足・追加・内容変更を target ごとに表示 |

`--expected-manifest /path/to/intended/apm.yml` を加えると、実際に読まれる manifest が意図した実体か確認できる。たとえば別 worktree の manifest を編集していても、global の symlink が元 checkout を参照していれば `manifest-location-mismatch` になる。

ローカル path が同じ Git repository の別 worktree を指す場合は、内容が同じでも `source-checkout-mismatch` を表示する。他 repository の依存は対象外。別 clone は同じ Git common directory と判定できないため対象外になる。

APM lockfile version 1 の `local_path`、`virtual_path`、`resolved_commit`、`deployed_files`、`deployed_file_hashes` を使う。古い lock にファイル別ハッシュがなければ `lock-content-unverified` を表示する。集約 `content_hash` を別の規則で再計算して一致と推測しない。APM の global lock が展開先を `.agents/...` のような相対表記で記録していても、global scope の home を基準に照合する。

## 結果の読み方

- 終了値 `0`: 対象スキルがあり、manifest・lock・commit・両 target の照合に指摘がない。
- 終了値 `1`: 不一致、照合不能、または対象スキルなし。各 target の `status` は独立しているため、片側だけ一致する状態も分かる。
- 終了値 `2`: manifest/lock の形式、読み取り権限、ローカル commit など入力の問題で照合を完了できない。

APM 0.29 の[公式ハッシュ実装](https://github.com/microsoft/apm/blob/v0.29.0/src/apm_cli/utils/content_hash.py)に従い、lock のファイル別ハッシュは UTF-8 text の CRLF を LF に正規化する。NUL、不正 UTF-8、単独 CR はそのまま保持する。一方、正本・cache・展開実体の比較は byte 単位で行うため、改行だけの差も内容差として表示する。cache 直下の `.apm-pin` は APM が生成する管理用ファイルとして source 比較から除外する。

`source-content-mismatch` は参照先や cache と対象 commit の差、`lock-content-mismatch` は記録されたファイル別ハッシュと対象 commit の差、`deployment-content-mismatch` は実際の展開内容と対象 commit の差を表す。lock の記録不足は、展開内容が一致していても完全一致にはしない。両 target の設定がなければ `target-not-configured` を示す。

シンボリックリンクを含む skill は照合不能とし、その参照先をたどらない。`__pycache__` と `.pyc` は runtime の生成物として内容比較から除外する。実行権限や skill の判断品質は評価しない。並行した編集・install を止める仕組みはないため、安定した状態で実行する。

出力はパス、commit、差分ファイル名、診断コードに限定し、ファイル本文は出さない。パスにも私的情報が含まれ得るため、実環境の JSON を公開 repository に保存しない。品質評価と実環境の一致率は別に報告する。

## 合成テスト

```sh
python3 -m unittest tests.test_check_apm_deployment
```

一時 Git repository と展開ディレクトリを使い、旧版、片側更新、別 worktree、変更なし、SHA pin、scope 分離、記録不足、改行ハッシュ、partial clone、読み取り拒否、入力不備などを確認する。全体の inventory と回帰テストの実行は root の `AGENTS.md` にある既存コマンドを使う。
