---
name: host-artifact
description: agent が生成した HTML、SVG、画像、PDF、静的 directory を、workspace と成果物名に紐づく安定 URL でブラウザ閲覧可能にするときに使う。機密情報、dynamic application、byte-for-byte snapshot、public Internet 公開には使わない。
---

# Host Artifact

ブラウザで自然に確認する静的成果物を生成したら、hosting の要否や Tailscale の有無を user に質問せず publish し、検証済み URL を返す。ブラウザは自動起動しない。

## Workflow

1. 成果物の意味を表す canonical slug を決める。1〜64文字の lowercase ASCII、数字、単一 hyphen だけを使う。
2. HTML、SVG、PDF、PNG、JPEG、GIF、WebP、AVIF、または top-level に `index.html` を持つ静的 directory を publish する。

   ```sh
   host-artifact publish <file-or-directory> --name <artifact-name>
   ```

3. JSON の `url` を返す。`transport: localhost` の場合だけ、同じ Mac からのみ閲覧可能であることを短く添える。同じ workspace/name の再 publish は同じ URL の新 revision になる。
4. 削除を user が明示した場合だけ、現在の workspace の全 revision を名前で削除する。

   ```sh
   host-artifact remove --name <artifact-name>
   ```

5. service と transport の確認には `status` を使う。Tailscale 利用者が remote 閲覧を初回設定すると明示した場合だけ `setup` を使う。通常の publish は設定を変更しない。

## Contract

- workspace は cwd から trusted helper が解決し、agent は artifact ID や公開 scope を管理しない。
- publish は元 source ではなく immutable revision copy を配信し、完成後に `current` を atomic に切り替える。
- HTML file と directory の entry HTML は標準で live reload し、元 source は変更しない。
- Tailscale Serve が設定・検証済みなら HTTPS URL、そうでなければ検証済み localhost URL を自動選択する。
- `/` の shelf から current artifact を再発見できる。artifact と revision は自動失効しない。
- symlink、dotfile、特殊 file、および top-level `index.html` のない directory は拒否する。
- GET/HEAD は revision header、body SHA-256 の ETag、`Cache-Control: no-store`、`nosniff` を返す。
- `setup` は Tailscale Serve の同一設定には idempotent で、競合設定、Funnel、login、tailnet 管理設定を変更しない。

## Safety

- tailnet 内から推測・閲覧されてもよい成果物だけを publish する。機密情報を含む成果物は local-only にせず、artifact 化しない。
- dynamic application、任意 server、public Internet、LAN、Tailscale Funnel には使わない。
- byte-for-byte の HTML snapshot や inline script を拒否する CSP が必要な成果物には使わない。
