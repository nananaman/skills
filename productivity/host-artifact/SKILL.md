---
name: host-artifact
description: agent が生成した単一 file または静的 directory を snapshot として localhost へ配信し、明示依頼時には Tailscale URL も案内するときに使う。dynamic application、public Internet、LAN 公開には使わない。
---

# Host Artifact

静的成果物を共通の常駐 service から capability path で配信する。

## Workflow

1. user が配信を依頼した成果物だけを指定する。既定は同じ Mac の loopback だけから取得できる。

   ```sh
   host-artifact host <file-or-directory>
   ```

   Tailscale 経由の閲覧が明示された場合だけ `--tailscale` を付ける。

   ```sh
   host-artifact host <file-or-directory> --tailscale
   ```

2. JSON output の `urls.localhost` を返す。
   `--tailscale` を指定した場合だけ `urls.tailscale` も返す。
   CLI は localhost の成果物 route を実際に取得し、Tailscale URL は対応 listener の bind 完了も確認してから返す。
   Tailscale listener が期限内にreadyにならない場合は、検証済みの `urls.localhost` と `tailscaleUnavailable` を返す。
3. 配信が不要になり user が削除を依頼した場合は、host 時に返された ID だけを削除する。

   ```sh
   host-artifact remove <artifact-id>
   ```

4. service 状態だけを確認する場合は `status` を使う。artifact 一覧は取得しない。

   ```sh
   host-artifact status
   ```

## Contract

- `host` は入力を配信 root へコピーし、元 file を直接公開しない。
- `host-artifact` command は Bun で checked-in TypeScript を直接実行する。生成済み JavaScript を配布物に含めない。
- 配信 root は service activation が事前に作成する。CLI は root や親 directory を作成せず、実 directory でない場合は停止する。
- 既定の ID は `local-<32hex>` で loopback listener だけから配信する。`--tailscale` の ID は `tailscale-<32hex>` で loopback と Tailscale listener の両方から配信する。
- file と directory 内の symlink、dotfile、特殊 file は拒否する。
- directory は top-level に通常 file の `index.html` を持つ場合だけ配信する。
- directory listing、artifact listing、未知 capability path は公開しない。
- service が unhealthy の場合だけ、固定 command `host-artifact-service ensure` で対象 service の起動を確認する。
- 正常にURLを返した成果物は自動失効しない。削除は user の明示依頼と発行済み artifact ID がある場合だけ行う。
- hostと同じ実行内でURL検証に失敗した場合は、未完了のcopyだけをrollbackする。rollbackにも失敗した場合は、検証失敗と削除失敗の両方を報告する。

## Safety

- capability path は強い認証ではない。機密情報を含む成果物を配信する前に user の依頼範囲を確認する。
- Tailscale URL を LAN または public Internet の URL として扱わない。
- 任意 service の起動、停止、再起動や publish root 外の削除を行わない。
