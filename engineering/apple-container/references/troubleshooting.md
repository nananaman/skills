# 症状別 troubleshooting

## 調査の基本

削除、prune、再インストールを最初に行わない。失敗した exact command、error、exit status、直前の変更を保存し、次の基本情報を採取する。token、credential、環境変数の secret は共有前に除く。

```sh
sw_vers
container --version
container system version --format json
container system status --format json
container system logs --last 1h
```

再現 command に `--debug` を付けると CLI の追加情報を得られる。

## `system status` / `system version` が失敗する

観察:

```sh
container system status --format json
container system version --format json
container system logs --last 1h
container --version
sw_vers
```

command sandbox 内では、`system status` の JSON が `status: "unregistered"` でも、それだけで API server の到達不能とは判定しない。まず `system version` の JSON に API server の version / build / commit が含まれるか確認する。通常の container lifecycle も検証対象なら、`sh` と `sleep` を使える既存の local image で一意名の disposable container を作成し、観察後にその container だけを停止・削除する。

```sh
status_check="status-check-$(uuidgen | tr '[:upper:]' '[:lower:]')"
status_check_created=0
cleanup_status_check() {
    if [ "$status_check_created" -eq 1 ]; then
        container stop "$status_check" || true
        if container delete "$status_check" || container delete --force "$status_check"; then
            status_check_created=0
        fi
    fi
}
trap cleanup_status_check EXIT INT TERM

if container run -d --name "$status_check" ALREADY_LOCAL_IMAGE sh -c 'echo status-check-ready; sleep 300'; then
    status_check_created=1
    container inspect "$status_check"
    container logs "$status_check" | grep -F status-check-ready
fi
cleanup_status_check
trap - EXIT INT TERM
```

`system version` で API server を確認でき、この lifecycle も成功するなら、runtime 切断ではなく launchd registration の可視性だけが sandbox に制限されている可能性が高い。この比較だけを理由に service を再起動したり、既存 container、kernel、DNS を変更したりしない。command sandbox が `container system logs` の内部 command を拒否しても、通常の `container logs APP` や lifecycle 操作が成功する場合があるため、別の失敗として記録する。

`system version` の JSON に CLI だけあり API server がない、または `status` が health check に失敗するなら service が未起動か応答不能である。system log に kernel 未設定、設定 file parse、service 起動のどこで失敗したかを探す。upgrade 直後なら CLI と API server の version / commit が揃うか確認し、停止・起動を一度行う。

```sh
container system stop
container system start
container system status
```

kernel 未設定が明示された場合だけ `container system kernel set --recommended` を実行する。設定 error なら `container system property list` と `~/.config/container/config.toml` の直前の変更を照合する。

## Application が即時終了する

観察:

```sh
container list --all --format json
container inspect APP
container logs APP
container logs --boot APP
```

application stdout / stderr に error があれば image の entrypoint、command、environment、workdir、mount を `inspect` と起動 command で照合する。application log が空で boot log に失敗があれば VM / init 側へ切り替える。対話的に image の中身を確認する場合は新しい一時 container を使う。

```sh
container run --rm -it --entrypoint /bin/sh IMAGE
```

PID 1 の signal forwarding や zombie reap が問題なら、同じ command を `--init` 付きで再現する。

## VM / machine が boot しない

観察:

```sh
container machine list --format json
container machine inspect MACHINE
container machine logs --boot MACHINE
container machine logs -n 200 MACHINE
container system logs --last 1h
```

custom machine image では `/sbin/init` の存在と executable bit、init の依存 file を確認する。custom kernel または nested virtualization を設定している場合は `inspect` の `kernel` と `virtualization`、host 要件を確認する。

既存 machine の永続設定は比較診断のために変更しない。同じ image を system 既定 kernel、nested virtualization 無効、home 非共有の一意名 machine として作成し、boot 結果を比較する。`create` が成功したときだけ、その一意名を後続の観察と cleanup に使う。

```sh
boot_check="boot-check-$(uuidgen | tr '[:upper:]' '[:lower:]')"
if container machine create --home-mount none --name "$boot_check" IMAGE; then
    container machine inspect "$boot_check"
    container machine logs --boot "$boot_check"
    container machine run -n "$boot_check" -- uname -a
    container machine delete "$boot_check"
fi
```

`delete` は machine の永続 filesystem も削除する。この script は、自身の `create` が成功した一意名だけを同じ block 内で削除し、同名の既存 machine や調査対象 `MACHINE` を cleanup 対象にしない。

## Architecture / `Exec format error`

観察:

```sh
uname -m
container image inspect IMAGE
container run --rm --arch arm64 IMAGE uname -m
container run --rm --arch amd64 IMAGE uname -m
container logs --boot CONTAINER
```

Apple `container` の guest application 対応は `linux/arm64` native と `linux/amd64` Rosetta の 2 種類である。image manifest に要求 architecture があるかを `image inspect` で確認し、`--platform linux/arm64` または `--platform linux/amd64` を明示する。その他の architecture を指定して pull や VM 作成まで進んでも、guest process は `Exec format error` になりうる。

## Build / builder が失敗する

観察:

```sh
container builder status --format json
container system df --format json
container build --progress plain --tag repro:debug .
container system logs --last 1h
```

plain progress で失敗した Dockerfile instruction と message を特定し、build context、`.dockerignore`、secret、base image、target platform を確認する。memory 不足が示された場合は、その build だけ resource を増やして比較する。

```sh
container build --cpus 8 --memory 16g --progress plain --tag repro:debug .
```

builder 全体の resource を変える必要がある場合だけ再作成する。これは builder state を削除する操作なので、ログ取得後に行う。

```sh
container builder stop
container builder delete
container builder start --cpus 8 --memory 16g
```

## Registry authentication / pull / push が失敗する

観察:

```sh
container registry list --format json
container image pull REGISTRY/OWNER/IMAGE:TAG --progress plain
container image push REGISTRY/OWNER/IMAGE:TAG --progress plain
```

registry host、repository path、tag、要求された scope を確認する。credential を更新するときは argv や shell history に token を置かない。

```sh
printf '%s\n' "$REGISTRY_TOKEN" | container registry login --username USER --password-stdin REGISTRY
container registry list
```

調査結果へ token、password、credential store の内容を貼らない。

## Port に接続できない / DNS・network が解決しない

観察:

```sh
container list --all --format json
container inspect APP
container network list --format json
container network inspect NETWORK
container logs APP
curl -v http://127.0.0.1:HOST_PORT/
```

`inspect` で publish の host IP / port、container port、protocol と最初の network attachment を照合する。application が container 内で想定 port を listen しているかを確認する。

```sh
container exec APP sh -c 'ss -lntup || netstat -lntup'
```

container 間通信では双方が同じ network に接続されているか、名前と設定 domain が合うかを確認する。

```sh
container system property list
container exec APP getent hosts PEER.test
```

host access 用 `--localhost` domain は macOS restart で packet-filter rule が消える。登録状態を確認し、必要な場合だけ管理者権限で作り直す。

```sh
container system dns list --format json
sudo container system dns create host.container.internal --localhost 203.0.113.113
```

## Mount が見えない / volume data が残らない

観察:

```sh
container inspect APP
container volume list --format json
container volume inspect VOLUME
container exec APP mount
container exec APP ls -la /EXPECTED/PATH
```

bind mount の host source と container target、`readonly`、named / anonymous volume ID を照合する。永続性は同じ volume に marker を書き、container を作り直して確認する。

```sh
persistence_id="$(uuidgen | tr '[:upper:]' '[:lower:]')"
persistence_volume="persist-check-${persistence_id}"
persistence_writer="persist-writer-${persistence_id}"

if container volume create "$persistence_volume"; then
    if container create --name "$persistence_writer" --volume "$persistence_volume:/data" alpine sh -c 'date > /data/marker'; then
        container start --attach "$persistence_writer"
        container run --rm --volume "$persistence_volume:/data" alpine cat /data/marker
        container delete "$persistence_writer"
    fi
    container volume delete "$persistence_volume"
fi
```

一意名の volume を作成できた場合だけ writer を作成し、writer を作成できた場合だけ marker の書き込みと読み戻しへ進む。最後に、この block 自身が作成した writer と volume だけを削除する。`--rm` は anonymous volume を削除しない。消失ではなく別の anonymous volume を再作成している可能性があるため、`volume list` と各 container の `inspect` で ID を照合する。

## Disk 使用量が増え続ける

観察:

```sh
container system df
container system df --format json
container list --all --format json
container image list --format json
container volume list --format json
```

`df` の image、container、volume の size と reclaimable を見て増加源を特定する。削除対象を `inspect` し、必要 data を退避してから個別に削除する。まとめて整理する場合も、対象を列挙してから該当 resource の prune を使う。

```sh
container prune
container image prune
container volume prune
container network prune
```

`image prune --all` は未使用の tagged image も対象にするため、通常の `image prune` より広い。診断 evidence を失う system data reset や手動 directory 削除は行わない。
