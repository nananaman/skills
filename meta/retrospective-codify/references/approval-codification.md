# Approval Codification

この branch は、同種の permission prompt が反復した、またはユーザーが特定操作を今後は確認なしで実行したいと明示した場合だけ使う。
一時 approval を観測しただけでは起動せず、永続化の採用指示までは設定を書き換えない。

## Outcome

反復操作を止めている全 enforcement layer を特定し、外部副作用に見合う最小 scope の永続 policy を一組の候補として提示する。
採用後は各 layer の source-of-truth を更新し、実操作を再実行せず静的な policy query で境界を検証する。

## Workflow

1. **観測を固定する**
   - approval を要求した exact executable、argv、実行元、表示理由、承認先を記録する。
   - transcript は不安定な補助情報として扱い、可能なら approval log、sandbox audit、現行 rules、`why` / policy check の結果を根拠にする。
   - 同じ操作が反復した証拠、またはユーザーの明示的な恒久化意図がなければ `temporary` として終了する。
   - completion: 恒久化候補にする根拠と exact invocation がある。

2. **全 enforcement layer を列挙する**
   - agent 自身の execpolicy / approval policy、外側の sandbox command policy、managed requirements、MCP / app 固有 approval を分ける。
   - 一つの layer を allow にしても別 layer が prompt / deny する場合は、部分解を完成案として提示しない。
   - 編集不能な managed layer や、永続 allow を表現できない app approval があれば blocker として示す。
   - completion: 各 layer が `allow` / `prompt` / `deny` / `not applicable` / `unknown` のいずれかに分類されている。

3. **最小 scope と副作用を判定する**
   - executable の実体を固定し、argv は目的を満たす最短の exact prefix または列挙で表す。
   - read-only、local write、remote create/update、publish、delete、credential/config change の順に副作用を分類する。
   - shell wrapper、wildcard、substitution、任意 API 呼び出し、任意 script 実行を含む broad allow は候補にしない。
   - remote create/update などを allow にする場合は、ユーザーがその操作クラスを恒久化すると明示したことを採用条件にする。
   - completion: match / near-miss / dangerous-neighbor の例と、副作用分類が揃っている。

4. **dedup と source-of-truth を確認する**
   - 各 layer の実効設定と配布元を確認する。展開物、symlink 先、自動生成物を直接編集しない。
   - 既存 rule が完全一致なら追加せず、広すぎる既存 rule があれば新規追加ではなく narrow 化候補として報告する。
   - completion: layer ごとの artifact、所有者、重複判定が明示されている。

5. **一組の proposal を提示する**
   - `retrospective-codify` の `[approval policy]` として、操作、全 layer の変更、最小 scope、副作用、検証 command を一項目にまとめる。
   - layer ごとに別番号へ分割しない。一部だけ採用されると approval が残るか境界が崩れるためである。
   - lifecycle hook を使う場合、hook は候補収集または retrospective の起動だけを行い、永続 policy を自動編集しない。
   - completion: ユーザーが一項目の採否で全 layer の変更を判断できる。

6. **採用後に更新・検証する**
   - 採用された proposal だけを各 source-of-truth へ反映する。
   - agent execpolicy は、その実装が提供する check command で match / near-miss / dangerous-neighbor を検証する。
   - nono command policy は profile validate と `nono why --command` で allow / approve / deny の近接境界を検証する。
   - GitHub resource 作成、publish、delete などの外部副作用は検証目的で実行しない。
   - completion: 全 layer の静的検証が通り、未検証 layer と残る risk が報告されている。

## Proposal fields

`[approval policy]` 候補には次を含める。

- Operation: 人間が意図を判断できる操作名
- Evidence: 反復の根拠、またはユーザーの明示指示
- Side effect: 副作用分類
- Layers: 現在の判定から変更後の判定
- Scope: executable と argv prefix / alternatives
- Artifacts: layer ごとの source-of-truth
- Boundary cases: match / near-miss / dangerous-neighbor
- Verification: 外部副作用を起こさない check commands

## Stop conditions

- approval の発生源または実効 layer が不明なら `unknown` として提案を止める。
- credential/config change、任意 shell、任意 API、delete を恒久 allow にする依頼は、より狭い operation へ分解できるまで書き出さない。
- source-of-truth が repository 外で変更権限がない場合は、patch 案と対象だけを提示する。
- 一度の approval は恒久化の承認ではない。採用指示を別に得る。
