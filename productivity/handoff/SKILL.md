---
name: handoff
description: 現在の会話を、別の agent が引き継げる handoff document に圧縮する。
argument-hint: "次の session で何をする予定か"
disable-model-invocation: true
---

現在の会話を要約し、新しい agent が作業を継続できる handoff document を作成する。
保存先は現在の workspace ではなく、ユーザーの OS の一時ディレクトリにする。

document には「suggested skills」section を含め、次の agent が使うべき skill を提案する。

PRD、計画、ADR、issue、commit、diff など、既存の artifact に記録済みの内容は重複して書かない。
代わりに path または URL で参照する。

API key、password、個人情報などの機微情報は redact する。

ユーザーが引数を渡した場合は、それを次の session の focus とみなし、その内容に合わせて document を調整する。
