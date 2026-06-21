# Learning Record Format

Learning record は `./learning-records/` に置き、`0001-slug.md`, `0002-slug.md` のように連番にする。最初の記録を書く時点で directory を作る。

これは teaching 版 ADR である。非自明な学び、重要な insight、今後の lesson を左右する前提知識を記録し、近接発達領域を推定する材料にする。

## Template

```md
# {Short title of what was learned or established}

{1-3 文。何が学ばれた/確立されたか。それが今後の session にとってなぜ重要か。}
```

基本はこれだけでよい。価値は項目を埋めることではなく、「今後の teaching 判断を変える知識」を短く残すことにある。

## Optional sections

必要な場合だけ入れる。大半の record には不要。

- **Status** frontmatter (`active | superseded by LR-NNNN`): 後で理解が更新された場合に使う。
- **Evidence**: ユーザーが理解を示した証拠。後で見直しそうな claim で有用。
- **Implications**: これにより次に何が可能/不要になるか。非自明な場合だけ書く。

## Numbering

`./learning-records/` の既存ファイルから最大番号を探し、1 つ増やす。

## When to write

次のいずれかを満たすときに書く。

1. **ユーザーが非自明な理解を示した。** 単なる exposure ではなく、概念を使えた証拠がある。
2. **ユーザーが前提知識を開示した。** 「X は知っている」。深さも記録する。
3. **誤解が修正された。** 関連 topic で再発しやすい stumbling block なので価値が高い。
4. **mission が learning によって変化した。** `MISSION.md` を更新し、record からも参照する。

## What does not qualify

- ただ扱っただけの教材。coverage は learning ではない。
- `GLOSSARY.md` の短い定義で十分なもの。
- session log。learning record は日記ではなく decision-grade insight。

## Supersession

後続 record が過去 record と矛盾する場合、古い record は削除せず `Status: superseded by LR-NNNN` と書く。理解の変化も有用な signal である。
