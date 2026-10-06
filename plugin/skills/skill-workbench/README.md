# Skill Workbench

実行結果から更新方向を作る内側のループと、候補アーカイブから構造を探索する外側のループを扱う。
入口は [SKILL.md](SKILL.md)、実行方法は[実験データと CLI](references/experiment-contract.md)。

## 設計方針

- 実行結果から原因仮説を作り、編集範囲を絞って候補を比較する。関連する過去の診断と反証を参照し、同じ追記を繰り返さない。
- agent が診断・編集を行い、Python が候補保存、Codex 実行、採点保存、比較、診断の根拠検査を行う。モデル呼出しを内包した自動 optimizer ではない。
- 改善を主張する前に実行比較する。比較基盤のテスト成功は、skill の有効性の証明ではない。
- 探索用アーカイブと採用版を分ける。現行 skill の廃止・統合・コード化も探索できる。
- 評価器と task の成果を切り離さない。合格条件の誤りや実行環境の混入も確認する。
- 採用版が自己評価器を同時に更新して合格する循環を避ける。評価変更は別の suite 版として比較し直す。

## 参考資料

- [SkillOpt](https://arxiv.org/abs/2605.23904)：実行結果からの編集、編集量の制御、検証による更新の採否。
- [SkillGrad](https://arxiv.org/abs/2605.27760)：診断の蓄積と、skill の層に応じた更新。
- [DGM](https://arxiv.org/abs/2505.22954)：過去の候補を保存し、別の候補から探索を再開する考え方。
- [Anthropic skill-creator](https://github.com/anthropics/skills/tree/34040c9c568585f6929bedeaad110ad08f079624/skills/skill-creator)：成果物・実行記録の評価、独立した比較、評価項目への批評、人のフィードバック。

## リポジトリでの検証

```sh
python3 -m unittest tests.test_skill_workbench
python3 scripts/check-skill-inventory.py
python3 -m unittest tests/test_check_skill_inventory.py
```

実行 adapter は Codex CLI を必要とする。単体・結合テストでは CLI 境界に fake executable を使い、保存・採点・比較は実物で確認する。
