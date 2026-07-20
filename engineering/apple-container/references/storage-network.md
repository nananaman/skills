# Storage・network・DNS

## 用途

Apple `container` 1.1.x で host directory、永続 volume、port、隔離 network、local DNS を構成する。

## Bind mount と一時 filesystem

host directory を container に read-write または read-only で共有する:

```sh
container run --rm --volume "${HOME}/project:/work" alpine ls /work
container run --rm --mount "source=${HOME}/project,target=/work" alpine ls /work
container run --rm --mount "source=${HOME}/project,target=/work,readonly" alpine touch /work/test
```

`--volume` / `-v` の bind 書式は `HOST_PATH:CONTAINER_PATH`。`--mount` は comma 区切りの `source=...,target=...,readonly` で、`readonly` を付けると container から書き込めない。container path は absolute path を使う。relative な host source は CLI の現在の作業 directory を基準に解決される。

root filesystem を read-only にし、書き込みが必要な path だけ tmpfs にする:

```sh
container run --rm --read-only --tmpfs /tmp --tmpfs /run my-app:latest
```

## Anonymous volume と named volume

container path だけを指定すると anonymous volume を作る。`--rm` で container を消しても anonymous volume は自動削除されない。

```sh
container run --rm --volume /var/lib/app my-app:latest
container volume list
container volume delete ANONYMOUS_VOLUME_ID
```

名前付き volume を作成し、container に mount する:

```sh
container volume create -s 10g app-data
container run -d --name app --volume app-data:/var/lib/app my-app:latest
container volume list
container volume inspect app-data
container stop app
container delete app
container volume delete app-data
container volume prune
```

使用中 volume は削除できない。`prune` は container から参照されていない volume をまとめて削除する。

### volume create の option

| 目的 | option と挙動 |
| --- | --- |
| 容量 | `-s SIZE`、または `--opt size=SIZE`。両方なら `-s` が優先する |
| journal mode | `--opt journal=ordered`、`--opt journal=writeback`、`--opt journal=journal` |
| journal 容量 | mode の後ろへ `:SIZE` を付ける。例: `--opt journal=writeback:64m` |

`ordered` は metadata を journal 化し data を metadata より先に書く。`writeback` は metadata のみで data の順序を保証しない。`journal` は metadata と data の両方を journal 化する。

```sh
container volume create --opt journal=ordered app-data
container volume create --opt journal=writeback:64m cache-data
container volume create --opt journal=journal audit-data
```

## Port を localhost に公開する

`--publish` / `-p` の書式は `[HOST_IP:]HOST_PORT:CONTAINER_PORT[/PROTOCOL]`。protocol の既定は TCP で、TCP または UDP を指定できる。

```sh
container run -d --name web --publish 127.0.0.1:8080:8000 web:latest
container run -d --name web6 --publish '[::1]:8080:8000' web:latest
container run -d --name dns-server --publish 127.0.0.1:5353:53/udp dns:latest
```

複数 network に接続した container では、公開 port は最初の network interface の IP へ転送される。

## Default network と隔離 network

`container system start` は `default` network を作り、`--network` を省略した container を接続する。追加 network は default や他の network から隔離される。

```sh
container network create app-net
container network create database-net --subnet 192.168.100.0/24 --subnet-v6 fd00:1234::/64
container network list
container network inspect database-net
container run -d --name db --network database-net postgres:latest
container run --rm --network default,mac=02:42:ac:11:00:02 alpine cat /sys/class/net/eth0/address
container stop db
container delete db
container network delete database-net
container network prune
```

| 操作 | command / option と挙動 |
| --- | --- |
| IPv4 subnet | `container network create NAME --subnet CIDR` |
| IPv6 subnet | `container network create NAME --subnet-v6 CIDR` |
| 接続 | `container run --network NAME IMAGE`。複数回指定して複数 network へ接続できる |
| MAC address | `--network NAME,mac=02:42:ac:11:00:02` |
| 確認 | `container network list`、`container network inspect NAME` |
| 削除 | `container network delete NAME`。container が接続中なら削除できない |
| 整理 | `container network prune` で未使用 network を削除する |

custom MAC は colon または hyphen 区切りの 6 octet とし、第一 octet の下位 2 bit を `10`（local-administered unicast）にする。未指定時は自動生成される。

明示的な subnet option を付けずに新規作成する network の既定 subnet は `~/.config/container/config.toml` で指定する。

```toml
[network]
subnet = "192.168.100.0/24"
subnetv6 = "fd00:abcd::/64"
```

設定は変更後に作成する network へ適用される。既存 network の subnet は変更しない。

## Local DNS と host access

名前付き container は組み込み DNS により `CONTAINER_NAME.DOMAIN` で解決できる。既定 domain は `test`。macOS 側からこの domain を使うには resolver を作成する。

```sh
sudo container system dns create test
container system dns list
sudo container system dns delete test
```

container から macOS host の localhost service へ接続するには、衝突しにくい IPv4 address を local domain に割り当てる。

```sh
python3 -m http.server 8000 --bind 127.0.0.1
sudo container system dns create host.container.internal --localhost 203.0.113.113
container run --rm alpine/curl curl http://host.container.internal:8000
container system dns list
sudo container system dns delete host.container.internal
```

`--localhost` を使う DNS domain の作成は macOS の packet-filter rule を追加し、Private Relay を無効にする。packet-filter rule は macOS の restart で消えるため、再起動後に host access が必要なら同じ `dns create --localhost` を再実行する。通常の container 間通信には `--localhost` を使わず、同じ network と container 名の DNS を使う。
