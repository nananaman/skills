# Container・image・registry

## 用途

Apple `container` 1.1.x で OCI workload を作成・実行・調査し、image を build・配布・保存する。mount、volume、port、network、DNS は `storage-network.md` を参照する。

## Container を実行する

一度だけ実行して終了後に削除する、対話 shell を開く、background で起動する例:

```sh
container run --rm alpine:latest echo hello
container run --rm -it ubuntu:latest /bin/bash
container run -d --name web nginx:latest
```

`run` は create と start を続けて行う。foreground が既定で、`-d` は container ID を表示して detach する。`-i` は stdin を開き、`-t` は TTY を割り当てる。終了後に container を残して再実行したい場合は `--rm` を付けない。

作成と起動を分ける:

```sh
container create --name job --env-file ./job.env alpine:latest /usr/local/bin/job
container start job
container start --attach job
```

`create` は VM を起動せず構成を保存する。`start` は既定で detach し、`--attach` を付けると process の出力へ接続する。

### run / create の主な option

| 目的 | option と挙動 |
| --- | --- |
| 名前 | `--name ID` |
| detach / 対話 | `-d`, `-i`, `-t`（対話 shell は `-it`） |
| 終了後に削除 | `--rm`。`run` で使う |
| 環境変数 | `-e KEY=VALUE`、`-e KEY`（host の値を継承）、`--env-file PATH`。複数回指定できる |
| 作業 directory | `-w PATH` / `--workdir PATH` |
| user | `-u USER[:GROUP]` / `--user`、または `--uid UID` と `--gid GID` |
| entrypoint | `--entrypoint COMMAND`。image の entrypoint を置換する |
| platform | `--platform linux/arm64` または `--platform linux/amd64`。`--os` / `--arch` より優先する |
| root filesystem | `--read-only` |
| CPU / memory | `--cpus 8 --memory 32g`。既定は 4 CPU / 1 GiB |
| shared memory | `--shm-size 1g` で `/dev/shm` の容量を指定する |
| tmpfs | `--tmpfs /tmp`。複数回指定できる |
| init | `--init` で PID 1 に signal forwarding と orphan reap を行わせる。`--init-image IMAGE` で VM init image を指定できる |
| capability | `--cap-add NAME`、`--cap-drop NAME`。複数回指定でき、drop の後に add が適用される |
| SSH agent | `--ssh`。host の SSH agent socket を container に転送する |
| nested virtualization | `--virtualization --kernel /absolute/path/to/vmlinux`。M3 以降と KVM 対応 kernel が必要 |

`arm64` は native、`amd64` は Rosetta 経由で実行する。capability 名は `CAP_` prefix の有無と大文字小文字を問わず、`ALL` も指定できる。

```sh
container run --rm --cpus 8 --memory 32g --read-only --tmpfs /tmp my-app
container run --rm --init --cap-drop ALL --cap-add SETUID --cap-add SETGID alpine id
container run --rm -it --ssh alpine sh
container run --rm --arch amd64 alpine uname -m
container run --rm --virtualization --kernel /opt/kernels/vmlinux-kvm ubuntu sh -c 'dmesg | grep kvm'
```

## Container の確認と操作

```sh
container list
container list --all
container list --all --format json
container inspect web
container logs web
container logs --boot web
container logs --follow -n 100 web
container exec -it web sh
container exec web ls /var/www
container stats
container stats --no-stream web
container stats --no-stream --format json web
```

`list` は実行中だけ、`--all` は停止済みも表示する。`inspect` は構成・状態・network・mount を確認する。`logs` は application の stdout / stderr、`--boot` は VM と init の boot log、`--follow` は追従、`-n N` は末尾 N 行を表示する。`stats` は既定で実行中 container を継続表示し、`--no-stream` は一度だけ取得する。

host と container の間で copy する:

```sh
container copy ./config.json web:/etc/app/config.json
container copy web:/var/log/app.log ./app.log

# 停止中なら先に起動する
container start web
container copy web:/var/log/app.log ./app.log
```

`copy` の alias は `cp`。container 側は `ID:/absolute/path` とし、片方を host path にする。copy 元または先の container は running でなければならない。停止中なら `container start ID` で起動してから copy する。

停止、signal 送信、削除、整理、filesystem export:

```sh
container stop web
container stop --signal SIGINT --time 30 web
container stop --all
container kill web
container kill --all
container delete web
container delete --force web
container delete --all
container prune
```

`stop` は既定で停止 signal を送り、5 秒後も終了しなければ SIGKILL にする。`kill` は即時に SIGKILL、`delete`（alias `rm`）は停止済みを削除し、`--force` は実行中も削除する。`prune` は停止済み container をまとめて削除する。

`export` は停止中の container にだけ実行できる。必ず stop してから root filesystem を tar に出力する。

```sh
container stop web
container export --output web.tar web

container stop job
container export job > job.tar
```

## Image を build する

```sh
container build --tag my-app:latest .
container build --file docker/Dockerfile.prod --tag my-app:prod .
container build --build-arg NODE_VERSION=22 --target production --no-cache --tag my-app:prod .
container build --cache-in type=registry,ref=registry.example.com/me/my-app:buildcache --cache-out type=registry,ref=registry.example.com/me/my-app:buildcache,mode=max --tag my-app:latest .
container build --secret id=token,src=./token.txt --tag my-app:latest .
container build --output type=tar,dest=./my-app.tar .
container build --platform linux/arm64 --platform linux/amd64 --tag registry.example.com/me/my-app:latest .
```

最後の引数は build context。`--file` を省略すると context の `Dockerfile`、次に `Containerfile` を探す。

| 目的 | option と挙動 |
| --- | --- |
| Dockerfile | `-f PATH` / `--file PATH` |
| tag | `-t REF` / `--tag REF`。複数回指定できる |
| build argument | `--build-arg KEY=VALUE`。複数回指定できる |
| stage | `--target NAME` |
| cache | `--no-cache` で cache を使わない。`--cache-in type=TYPE,KEY=VALUE` で import、`--cache-out type=TYPE,KEY=VALUE` で export し、それぞれ複数回指定できる。registry cache は `type=registry,ref=IMAGE`、export mode は `mode=min|max` |
| base image | `--pull` で base image を再取得する |
| secret | `--secret id=ID,src=PATH` または `id=ID,env=ENV_NAME` |
| output | `--output type=oci`（既定）、`type=tar,dest=PATH`、`type=local,dest=DIR` |
| platform | `--platform linux/arm64 --platform linux/amd64`。`--arch arm64 --arch amd64` でも指定できる |
| builder resource | `--cpus N --memory SIZE` でその build の builder VM 資源を指定する |

builder を事前に大きな構成で起動する、または既存構成を作り直す:

```sh
container builder status
container builder start --cpus 8 --memory 32g
container builder stop
container builder delete
container builder start --cpus 8 --memory 32g
```

builder は別 VM で、既定は 2 CPU / 2 GiB。実行中 builder の資源を変えるときは stop、delete、start の順で再作成する。

## Image を管理する

```sh
container image pull alpine:latest
container image push registry.example.com/me/my-app:latest
container image list
container image list --format json
container image inspect my-app:latest
container image tag my-app:latest registry.example.com/me/my-app:v1
container image save --output images.tar my-app:latest alpine:latest
container image save my-app:latest > image.tar
container image load --input images.tar
container image delete my-app:latest
container image prune
container image prune --all
```

`tag` は同じ image に別の参照名を付ける。`save` は複数 image を tar に保存でき、`--output` を省略すると stdout に書く。`load` は tar を local store に読む。`prune` は未使用 image を削除し、`--all` は未使用の tagged image も対象にする。

## Registry に認証する

```sh
container registry login registry.example.com
printf '%s\n' "$REGISTRY_TOKEN" | container registry login --username me --password-stdin registry.example.com
container registry list
container registry logout registry.example.com
```

対話 `login` は username と password を prompt で受け取る。自動化では token を argv に含めず `--password-stdin` を使う。`list` は保存済み credential の registry を表示し、`logout` は対象 credential を削除する。
