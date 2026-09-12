# Audit ledger の修復

audit ledgerが `trailing characters` でparse不能なら、対象行を読み取り、複数の完全なJSON objectが改行なしで連結された場合だけ修復候補にする。対象ledgerと操作を示してユーザー承認を得た後、同じdirectoryへ既存fileを上書きしない名前でbackupし、object境界へ改行だけを戻して、境界前後のsessionを `nono audit verify <session-id>` で検証する。object欠損、曖昧な境界、chain不整合、backup失敗のいずれかがあれば自動修復せず停止する。
