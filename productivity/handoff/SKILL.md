---
name: handoff
description: 現在の会話を、別の agent が引き継げる引き継ぎ文書に圧縮する。
argument-hint: "次のセッションで何をする予定か"
disable-model-invocation: true
---

現在の会話を要約し、新しい agent が作業を継続できる引き継ぎ文書を作成する。
保存先は現在の作業領域ではなく、ユーザーの OS の一時ディレクトリにする。

文書には出力契約として「suggested skills」節を含め、次の agent が使うべき skill を提案する。

PRD、計画、ADR、issue、commit、diff など、既存の成果物に記録済みの内容は重複して書かない。
代わりにパスまたは URL で参照する。

API キー、パスワード、個人情報などの機微情報は伏せる。

ユーザーが引数を渡した場合は、それを次のセッションの主題とみなし、その内容に合わせて文書を調整する。
