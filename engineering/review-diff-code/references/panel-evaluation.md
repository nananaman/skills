# Panel Evaluation

reviewer数の増減は、prompt上のcoverageではなく実diffで比較して決める。

## Method

1. 変更前panelをbaselineとして残す。
2. 同じchange bundle、engine、model、thinkingでbaselineとcandidateを実行する。
3. 実変更のfindingを周辺コードとdocumented contractでaccepted / rejectedへ分ける。
4. 実変更がcleanなら、一時cloneへ既知のfailure modeをseedする。
   - behavioral / lifecycle
   - security / secret handling
   - type / API / serialization contract
   - ownership / maintainability
5. 少なくとも2回実行し、カテゴリ別の検出、unique accepted finding、false positive、wall time、reviewer数を比較する。
6. critical / high failure modeをcandidateだけが恒常的に落とす場合はdefaultへ採用しない。
7. 評価用seedはsource repositoryへ残さない。
