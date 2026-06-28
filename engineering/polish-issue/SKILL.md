---
name: polish-issue
description: draft issue または既存 issue を、実装前の不確実性を減らした implementation design contract へ磨く。repo の engineering flow / issue tracker / domain docs を読み、調査・検証・テスト実行までは行うが、正式な実装 diff は残さない。PRD / Design Doc 作成、通常実装、diff review だけの依頼では使わない。
---

# Polish Issue

issue を「別 agent がその issue だけを読んで実装に入れる」状態まで磨く。
成果物は polished issue であり、正式な実装 diff ではない。

## Contract

polished issue は implementation design contract である。
逐次手順書ではなく、実装時の判断ブレを減らす設計契約として書く。

見出しは原則日本語にし、「目的」「現状」「設計方針」「変更対象ファイル」「テスト方針」「完了条件」を明示する。

含めるもの:

- 目的と背景
- 優先度根拠（必要な場合）
- 現状
- 要求 / 仕様
- やらないこと
- 設計方針
- 変更境界 / 変更対象ファイル
- 必要な型定義案 / 擬似コード / 依存グラフ
- 採用しない案と理由
- 実装上の注意
- テスト方針
- 後方互換の影響（必要な場合）
- 完了条件
- PRD / Design Doc への link と必要十分な要約

含めないもの:

- 正式な実装 diff
- 無意味に細かい逐次手順
- 実装者の裁量を奪う過剰な指示
- 未検証の仮説を事実扱いする記述

## Safety

- この skill では `git commit`、`git push`、APM pin 更新、skill install を実行しない。
- この skill では PRD / Design Doc を編集しない。矛盾や不足を見つけたら issue を blocked にし、Design Doc 更新は別タスクに戻す。
- 実装対象コード・設定・テストの正式 diff を残さない。
- 永続化してよい変更は、確認済みの issue / tracker 文書だけである。

## Allowed during polish

実装不確実性を減らすために、次は許可する。

- コード読解
- 既存 test / spec / docs / issue の調査
- 小さな検証コード
- 型確認
- テスト実行
- 一時的な実験

ただし最終的に残してよい diff は、確認済みの issue / tracker 文書だけにする。
検証のために変更したコード・一時ファイルは、issue 更新前に戻すか削除する。

## Stop conditions

次の場合は issue を polished にせず blocked として止める。

- Design Doc が必要なのに存在しない
- Design Doc の主要判断に矛盾・不足・誤りがある
- PRD の scope / やらないことと矛盾している
- 実装に必要な未解決質問が残っている
- 検証で重大な前提崩れが見つかった

Design Doc の判断ミスを見つけた場合、issue 内で勝手に補正しない。
この skill では Design Doc / PRD を編集しない。issue を blocked にし、Design Doc 更新を別タスクとして戻してから再 polish する。

blocked 時は polished template を使わない。issue には次を残す。

```md
- 状態: Blocked
- ブロック元文書: <Design Doc / PRD link>
- ブロック理由: <矛盾・不足・誤り>
- issue 側で補正しない理由: <理由>
- 上流で必要な判断: <Design Doc / PRD 側で決めること>
- 再 polish 条件: <再 polish に入れる条件>
```

## Workflow

### 1. Load repo-local settings

必ず読む。

```text
docs/agents/engineering-flow.md
docs/agents/issue-tracker.md
docs/agents/domain.md
```

存在しない場合は `setup-engineering-flow` を提案して止める。

### 2. Locate target issue

`docs/agents/issue-tracker.md` に従って対象 issue を読む。

- GitHub Issue: `gh issue view` 等で読む
- Local markdown: issue markdown file を読む
- Other: 設定 prose に従う

PRD / Design Doc 参照があれば読む。
リンクだけで issue 実装に必要な情報が足りない場合は、issue 側に要約を追加する。

PRD / Design Doc 参照がない場合は、repo-local `engineering-flow.md` に従って必要性を判定する。
新機能・仕様変更で polished PRD がない場合は blocked にし、`draft-prd` / `polish-prd` に戻す。小バグ、小リファクタ、trivial docs/config、主に技術改善の Design Doc 起点作業は例外としてよい。
複数 issue に分割される変更、API / DB / 状態設計 / 互換性 / 移行 / 高い設計リスクに関わる変更で Design Doc がない場合は blocked にする。
不要と判断した場合は、issue の `参照` に `なし — 理由: ...` を明記する。

### 3. Grill the issue

一度に一つずつ問いを立て、必要なら調査して答える。
ユーザーに聞く前に、コードベースから答えられることは自分で調べる。

必ず詰める観点:

- なぜやるのか
- 何をやらないのか
- 完了をどう判定するのか
- 既存仕様・既存コードと衝突しないか
- 変更境界はどこか
- 代替案は何で、なぜ採用しないのか
- 実装上の落とし穴は何か
- テストで何を保証するのか

### 4. Investigate and verify

必要に応じてコード・テスト・spec を読む。
不確実性が高い場合は、小さな実験や test / typecheck を実行してよい。

検証前に worktree snapshot を取る。

```bash
git status --short --untracked-files=all
```

検証で worktree を変更した場合:

```bash
git diff --stat
git diff --name-status
git status --short --untracked-files=all
```

戻してよいのは、この skill が作った変更・一時ファイルだけである。開始前から存在したユーザー変更は戻さない。確認済みの issue / tracker 文書以外に、この skill が作った modified / staged / untracked が残っている場合は戻す。既存変更と区別できない場合は戻さず、polished にせず blocked として報告する。

### 5. Rewrite as polished issue

`../draft-issue/assets/issue-template.md` を seed にして polished body または blocked body を作る。
既存 issue の有用な情報は保持し、重複・曖昧な記述は統合する。

既存 issue に `<!-- TODO(polish): ... -->` コメントがある場合は、各 TODO を調査・検証で埋める。解決した TODO コメントは削除する。

`TODO(polish)` コメントは polished issue に残さない。実装に必要な TODO / open question が解決できない場合は必ず `Blocked` にする。`先送り事項` に移せるのは、この issue の実装契約に不要で scope 外として明示できる項目だけである。

更新前に polished body / blocked body をユーザーへ提示する。ユーザー確認後だけ GitHub Issue / local markdown issue / other tracker を更新する。

### 6. Validate polished gate

更新前に以下を自己確認する。

- issue だけで実装に入れるか
- PRD / Design Doc の重要判断が要約されているか
- scope / やらないことが明確か
- 変更対象と設計方針が具体的か
- テスト方針が実行可能か
- 実装に必要な unresolved open question がないか
- 先送り事項が、この issue の scope 外として明示できるものだけか
- `TODO(polish)` コメントが残っていないか
- 未確認事項を事実として書いていないか
- 空の見出しや埋め草の文が残っていないか
- 同じ内容が複数章で重複していないか
- `git status --short --untracked-files=all` で確認済みの issue / tracker 文書以外の modified / staged / untracked が残っていないか

### 7. Closeout

報告には次を含める。

- polished issue location / URL
- 調査・検証した内容
- 実行した test / typecheck / proof
- 残した deferred item があればその理由
- 実装へ進めるか、blocked か
- commit / push / APM pin 更新 / install は未実行であること
