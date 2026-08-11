# Herdr での Hunk review コメント回収

managed Hunk review pane は Herdr plugin と人間が管理する。
agent は pane を起動、reload、close せず、pane 表示をコメントの source of truth にしない。

人間がレビュー完了を伝えた後だけ、現在の repository について Hunk session と user comment を session API から取得する。
具体的な構文は `hunk session --help` と対象 subcommand の `--help` で確認する。

- session が見つからない場合は、コメント0件として扱わず session 未検出を報告する。
- コメントがある場合は、原文、file、line、hunk 情報を保持して整理する。
- コメントが0件の場合も自動承認せず、指摘なしとして進めてよいか確認する。
- コメント取得後、修正または commit へ進む前に対応方針を確認する。
- レビュー完了後も Hunk pane を close せず、watch を継続させる。
