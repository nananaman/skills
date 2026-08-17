# Herdr での command と agent の協調

隣接 pane で長時間 command を動かす場合や、helper agent と協調する場合の判断境界を定める。
具体的な引数は実行前に `herdr pane --help`、`herdr agent --help`、対象 subcommand の `--help` で確認する。

## Pane の観測と作成

既存 pane は current、list、get で対象を確認してから read する。
soft wrap が解析を妨げる場合は unwrapped source、TUI の見た目が必要な場合は ANSI format を選ぶ。

長時間 command、dev server、test、log tail、screenshot 取得のような一時作業も含め、現在 pane を占有したくない作業は、現在 tab を split した補助 pane を `--no-focus` で作って実行する。
agent が直前に作成した補助 pane は、`tests`、`dev server`、`logs`、`review`、helper の個別タスクなど、その pane 固有の label を付けてよい。
人間がファイル確認などに使う既存 pane と、その pane に人間が付けた label は変更しない。

直前に作成した補助 pane への run は通常操作として扱う。
それ以外の既存 pane への run、text、key の送信は、対象と内容を示してユーザーの承認を得る。

## 補助 pane の再取得

補助 pane へ run、send-text、send-keys する前に、`herdr pane process-info` で foreground process を確認する。
shell 以外が foreground にある pane は、人間が使い始めたか前の作業が残っているものとして扱い、入力、close、rename をしない。

この場合は承認を求めず、現在 tab を split した新しい補助 pane を `--no-focus` で作って作業を続ける。
放棄した pane ID、新しい pane ID、放棄した理由を報告する。
同一作業での作り直しは2回までとし、それを超える場合は状況を報告して止める。

## 待機

通常 command の出力は pane の wait-output、agent の状態は agent wait で待つ。
timeout は有限にし、完了後または timeout 後に read で実際の出力を確認する。

timeout または stalled の場合は、対象 pane の read と agent の get、read を使い、次を区別する。

- command または agent の失敗
- 補助 pane が人間に使われ始めた
- まだ実行中
- readiness marker の不一致
- 読み取り source の不一致
- agent state change の未検出

条件を変えて再試行する場合は、その理由を報告する。

## Helper agent

helper の具体的な依頼を決めてから、現在の working directory で補助 pane を `--no-focus` で作る。
split response の pane ID を保持し、その pane に個別タスクの label を設定してから agent を起動する。

- helper agent 名は pane label から生成する。正規化、長さ、一意化は[`session-naming.md`](session-naming.md)に従う。
- pane rename が失敗したら agent を起動しない。
- agent start が失敗した場合は pane label を保持する。再試行時は agent list を読み直して名前を再計算する。
- prompt、wait、read は agent 名より stable な helper pane ID を優先して target にする。
- helper への最初の prompt と待機を一操作にできる場合は、atomic な prompt command を使う。

## 承認が必要な操作

tab と workspace の作成、focus、close、attach、takeover、pane move、swap、resize、zoom、既存 pane や既存 agent への入力は、ユーザーが明示依頼した場合だけ実行する。
実行前に対象 ID、現在の process または agent 状態、操作、予想される影響を提示する。
