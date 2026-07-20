---
name: apple-container
description: Apple の container CLI 1.1.x で OCI image、container、network、volume、machine、system を操作・診断するときに使う。Docker / Podman 固有の Compose、第三者製 container-compose、Kubernetes、Swift Containerization API、container 本体の開発には使わない。
---

Apple 公式 `container` CLI 1.1.x の操作マニュアル。依頼内容に対応する reference を読んで、具体的なコマンドと option を選ぶ。

## Reference

| タスク | 読む reference |
| --- | --- |
| 動作要件、インストール、初回起動、upgrade、uninstall、既定設定 | [references/getting-started.md](references/getting-started.md) |
| container lifecycle、exec、logs、copy、build、image、registry | [references/containers-images.md](references/containers-images.md) |
| mount、volume、port publish、network、DNS | [references/storage-network.md](references/storage-network.md) |
| machine、kernel、system、resource、構造化出力 | [references/machine-system.md](references/machine-system.md) |
| application、VM、build、network、disk の症状別診断 | [references/troubleshooting.md](references/troubleshooting.md) |

複数領域にまたがる依頼では、該当する reference をすべて読む。

## 対象外

Docker / Podman 固有の Compose、第三者製 `container-compose`、Kubernetes、Swift Containerization API、Apple `container` 本体の開発・build は扱わない。1.1.x 以外や未記載の option を扱う場合は、その実機 version の help と公式文書を確認する。
