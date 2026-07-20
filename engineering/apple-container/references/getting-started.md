# 導入・起動・設定

## 用途

Apple `container` 1.1.x の動作要件を確認し、Homebrew で導入、起動、更新、削除する。CLI と service の version 確認、既定値の参照、`config.toml` による設定もここで扱う。

## 動作要件

- Apple silicon Mac
- macOS 26 以降
- kernel や image の取得に使うネットワーク接続

## インストールと初回起動

```sh
brew install container
container system start
```

初回の `container system start` では、既定の Linux kernel をダウンロードするか確認する prompt が表示される。内容を確認して承認すると kernel を取得し、system service が起動する。

起動状態、CLI と service の version、停止中を含む container を確認する。

```sh
container system status
container system version
container list --all
```

ログイン時に system service を自動起動したい場合は、Homebrew service として登録できる。

```sh
brew services start container
```

自動起動を解除する場合は次を使う。

```sh
brew services stop container
```

## Upgrade と uninstall

実行中の container と system service を止めてから formula を更新する。

```sh
container system stop
brew upgrade container
container system start
```

Homebrew 版を削除する。

```sh
container system stop
brew uninstall container
```

`brew uninstall` は CLI を削除する操作であり、作成済みの image や container などのデータ削除とは別である。

## 設定

既定設定は `~/.config/container/config.toml` に TOML で記述する。現在有効な property は通常表示または JSON で確認できる。

```sh
container system property list
container system property list --format json
```

設定できる section は次のとおり。

| section | 主な設定 |
| --- | --- |
| `[build]` | builder VM の `cpus`、`memory`、`rosetta`、`image` |
| `[container]` | `run` / `create` で使う既定の `cpus`、`memory` |
| `[dns]` | container 名に補完する `domain` |
| `[kernel]` | kernel の `binaryPath`、取得元 `url` |
| `[network]` | 新規 network の既定 `subnet`、`subnetv6` |
| `[registry]` | image 名で省略する registry の `domain` |
| `[vminit]` | `vminitd` の `image` |
| `[plugin.<id>]` | plugin 固有の設定 |

例:

```toml
[build]
cpus = 4
memory = "4gb"
rosetta = false

[container]
cpus = 4
memory = "1gb"

[dns]
domain = "test"

[network]
subnet = "192.168.100.0/24"
subnetv6 = "fd00:abcd::/64"

[registry]
domain = "ghcr.io"
```

`memory` は二進系（1024 基数）で解釈される。裸の整数は byte。suffix は `b`、`k` / `kb` / `kib`、`m` / `mb` / `mib`、`g` / `gb` / `gib`、`t` / `tb` / `tib`、`p` / `pb` / `pib` を使える。

`subnet` と `subnetv6` は address と prefix length を組み合わせた CIDR 文字列で指定する。IPv4 は `"192.168.100.0/24"`、IPv6 は `"fd00:abcd::/64"` の形式を使う。不正な CIDR は設定読み込み時に error になる。
