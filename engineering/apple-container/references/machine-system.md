# Machine・system 管理

## 用途

Apple `container` 1.1.x で、停止後も filesystem を残す Linux 環境を管理し、system service、kernel、disk 使用量を確認する。通常の application container の操作は `containers-images.md` を参照する。

## Container machine を作成・実行する

machine は OCI image から作る長期利用向け VM である。通常の container が image の command を PID 1 として実行するのに対し、machine は image の `/sbin/init` を起動する。root filesystem は stop 後も保持され、`run` は停止中なら起動してから command を実行する。

```sh
container machine create alpine:3.22 --name dev
container machine run -n dev
container machine run -n dev whoami
container machine run -n dev -- cat /proc/cpuinfo
container machine run -n dev --root id
```

初回 boot では host と同じ名前・UID・GID の user が作られ、既定では host の home directory が read-write で共有される。`--root` を付けない `run` はその user で実行する。

作成時に resource、home の共有方法、既定 machine を指定できる。

```sh
container machine create --cpus 4 --memory 8G --home-mount ro --set-default alpine:3.22
container machine create --no-boot --home-mount none alpine:3.22 --name isolated
container machine set-default dev
container machine run
```

`--home-mount` は `rw`（既定）、`ro`、`none`。machine の root filesystem が永続でも、host home は別の mount である。host file を変更させたくない場合は `ro`、共有自体が不要なら `none` を選ぶ。

## 一覧・調査・変更・削除

```sh
container machine list
container machine list --format json
container machine list --quiet
container machine inspect dev
container machine logs dev
container machine logs --boot dev
container machine logs --follow -n 100 dev
container machine set -n dev cpus=4 memory=8G home-mount=ro
container machine stop dev
container machine run -n dev -- nproc
container machine delete dev
```

`inspect` は JSON を返す。`set` の `cpus`、`memory`、`home-mount`、`virtualization`、`kernel` は停止して次に起動したとき反映される。CPU の既定は host core 数の半分（最低 4）、memory の既定は host memory の半分（最低 1 GiB）。`delete`（alias `rm`）は実行中なら停止してから永続 filesystem ごと削除するため、必要な data を先に退避する。

## Custom machine image と user 作成

custom image には executable な `/sbin/init` が必要で、systemd などの init system と長期 service を起動できる。

```dockerfile
FROM ubuntu:24.04
ENV container container
RUN apt-get update && apt-get install -y systemd sudo && rm -rf /var/lib/apt/lists/*
RUN systemctl set-default multi-user.target
```

```sh
container build --tag local/ubuntu-machine:latest .
container machine create local/ubuntu-machine:latest --name ubuntu
container machine run -n ubuntu -- systemctl is-system-running
```

既定の初回 user provisioning を差し替える場合は image に executable な `/etc/machine/create-user.sh` を置く。この script は初回 boot に root で一度だけ実行され、`CONTAINER_USER`、`CONTAINER_UID`、`CONTAINER_GID`、`CONTAINER_HOME`、`CONTAINER_MACHINE_ID` を受け取る。

## Nested virtualization と custom kernel

nested virtualization には M3 以降の Apple silicon、macOS 15 以降、`CONFIG_KVM=y` の custom kernel が必要で、既定 kernel は KVM に対応しない。

```sh
container machine create --virtualization --kernel /opt/kernels/vmlinux-kvm --name kvm-dev alpine:3.22
container machine run -n kvm-dev -- ls -l /dev/kvm
container machine set -n dev virtualization=true kernel=/opt/kernels/vmlinux-kvm
container machine stop dev
container machine run -n dev -- ls -l /dev/kvm
container machine set -n dev kernel=
```

最後の `kernel=` は machine 固有の override を解除する。

## System service

```sh
container system start
container system status
container system version
container system logs
container system logs --last 1h
container system logs --follow
container system df
container system stop
```

`status` は API server の health check、`version` は CLI と応答可能な API server の version、build、commit を表示する。`system logs` の既定範囲は直近 5 分で、`--last` は `m`、`h`、`d` 単位を受け取る。`df` は image、container、volume ごとの総数、active 数、size、reclaimable を表示する。

初回起動の kernel prompt を明示的に制御する場合:

```sh
container system start --enable-kernel-install
container system start --disable-kernel-install
```

## System kernel を選ぶ

推奨 kernel を取得して既定にする:

```sh
container system kernel set --recommended
```

tar archive 内の binary、または手元の生 binary を指定する:

```sh
container system kernel set --tar https://example.invalid/kata.tar.zst --binary opt/kata/share/kata-containers/vmlinux.container
container system kernel set --binary /opt/kernels/vmlinux --arch arm64 --force
```

`--tar` は local path または URL、同時に使う `--binary` は archive member の path。`--binary` 単独なら kernel file の path である。`--recommended` は他の指定より優先し、`--force` は同名 kernel を上書きする。kernel architecture は `arm64`（既定）または `amd64`。guest application は `arm64` native と Rosetta による `amd64` を使えるが、通常の amd64 application 実行にも system kernel は arm64 で足りる。

## 構造化出力

automation では table を parse せず、対応 command の `--format` を指定する。

```sh
container system status --format json
container system version --format yaml
container system df --format toml
container system property list --format json
container machine list --format json
container machine inspect dev
```

`system status`、`version`、`df` は `table`、`json`、`yaml`、`toml`。`machine list` は `table` または `json`、`machine inspect` は常に JSON。`system property list` は `toml` または `json` を返す。
