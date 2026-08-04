---
name: host-artifact
description: agent が生成した HTML、SVG、画像、PDF、静的ディレクトリを、作業領域と成果物名に紐づく安定した URL でブラウザから閲覧可能にするときに使う。機密情報、動的アプリケーション、バイト単位のスナップショット、公開インターネットへの配信には使わない。
---

# Host Artifact

ブラウザで確認する静的成果物を生成したら、配信の要否や Tailscale の有無をユーザーに質問せず公開し、検証済みの URL を返す。ブラウザは自動起動しない。

## 手順

1. 成果物の意味を表す正規の slug を決める。1〜64 文字の小文字 ASCII、数字、単一のハイフンだけを使う。
2. HTML、SVG、PDF、PNG、JPEG、GIF、WebP、AVIF、または最上位に `index.html` を持つ静的ディレクトリを公開する。

   ```sh
   host-artifact publish <file-or-directory> --name <artifact-name>
   ```

3. JSON の `url` を返す。`transport: localhost` の場合だけ、同じ Mac からのみ閲覧可能であることを短く添える。同じ作業領域と名前で再公開すると、同じ URL の新しい版になる。
4. 削除をユーザーが明示した場合だけ、現在の作業領域にある全版を名前で削除する。

   ```sh
   host-artifact remove --name <artifact-name>
   ```

5. サービスと転送方式の確認には `status` を使う。Tailscale 利用者がリモート閲覧を初回設定すると明示した場合だけ `setup` を使う。通常の公開では設定を変更しない。

## 契約

- 作業領域は現在の作業ディレクトリから信頼済みの補助機能が解決し、agent は成果物 ID や公開範囲を管理しない。
- 公開時は元ファイルではなく変更不能な版の複製を配信し、完成後に `current` を不可分に切り替える。
- HTML ファイルとディレクトリの入口となる HTML は標準で自動再読み込みし、元ファイルは変更しない。
- Tailscale Serve が設定・検証済みなら HTTPS URL、そうでなければ検証済み localhost URL を自動選択する。
- `/` の一覧から現在の成果物を再発見できる。成果物と版は自動失効しない。
- シンボリックリンク、隠しファイル、特殊ファイル、および最上位に `index.html` のないディレクトリは拒否する。
- GET/HEAD は版を示すヘッダー、本文 SHA-256 の ETag、`Cache-Control: no-store`、`nosniff` を返す。
- `setup` は Tailscale Serve の同一設定に対して何度実行しても結果が変わらず、競合設定、Funnel、ログイン、tailnet の管理設定を変更しない。

## 安全上の制約

- tailnet 内から推測または閲覧されてもよい成果物だけを公開する。機密情報を含む成果物はローカル限定にせず、成果物として配信しない。
- 動的アプリケーション、任意のサーバー、公開インターネット、LAN、Tailscale Funnel には使わない。
- バイト単位で同一の HTML スナップショットや、インラインスクリプトを拒否する CSP が必要な成果物には使わない。
