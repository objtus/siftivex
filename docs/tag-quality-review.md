# タグのクオリティ考察（設計について）

> **状態**: 一部反映済み（2026-09-07）
> **対象**: `data/siftivex.db` の `image_tags`（auto=VLM / filename=ファイル名パーサー）
> **目的**: タグのクオリティ・一貫性について**設計の観点**から考察する
> **補足**: pixiv 由来（36,394 枚）は VLM 未通し・pixiv コミュニティタグのため本検証対象外。under.iphone 由来（3,926 枚・VLM 済み）を調査。

---

## 0. 前提（本章の前提条件）

本プロジェクトのタグフローは次のように成立している:

1. **ファイル名タグ（`filename`）** — プロジェクト以前に**手動で付与されたタグ**。初期タグシステムの基盤。
2. それを土台に**初級タグシステムを設計**。
3. **VLM（`auto`）で画像からタグを追加生成し、データベースに保存**。

このため **`filename` と `auto` が同一タグを別ソースとして DB に保存されることは意図通り**であり、保存そのものは問題にしない。

一方、**表示・検索・統計で結合する段階**（`effective_tags()` 等）では重複を除く設計が必要。本章で対象にするのは、**タグ生成・保存・結合の「設計」がクオリティ・一貫性にどう影響しているか**。

本章の考察は**単一の取り込み源（under.iphone）に特化した設計ではない**前提で読む。考慮すべき前提:

- **取り込みソースは複数**（under.iphone のほか、pixiv 由来や将来的な他ソースを想定）。
- **under.iphone は NSFW 系資料が多い源**だが、今後は NSFW 以外（実写・写真など）の取り込みも予定。
- したがって **under.iphone に特化・過剰適合した設計は好ましくなく、タグシステムは汎用性・拡張性を持たせる必要がある**。
- 本章の問題は under.iphone 由来も含まれるが、**汎用設計の観点では「別源が来たら同じ轍を踏まないか」の確認材料**として扱う。

---

## 1. 結論（先に）

タグのクオリティ・一貫性の低さは「VLM が悪い」ではなく、**設計の甘さ**による。具体的には以下の 7 問題。詳細は §2。

| ID | 問題 | 概要 |
|---|---|---|
| P1 | ソース間結合ルール欠如 | DB 上の filename/auto 二重保存は意図通りだが、結合時 dedup・優先順位が未設計（`effective_tags` が重複返却） |
| P2 | 非公式 namespace 風タグ | VLM が許容リスト外の slash 付きタグ（`靴のNR/BRソール` 等）を flat に出力 |
| P3 | ネスト規則不一致 | 同一概念でネスト／扁平がぶれる（`種類/文章/スクショ` vs `文章/スクショ`） |
| P4 | 同義 flat タグ共存 | `セーラー服` と `セーラー襟` のように同義タグが両方保存 |
| P5 | flat の上限未 enforce・外れ値 | 範囲 1〜428 グ。上限 max_flat_tags=60 がプロンプトのみで post-process 未適用 |
| P6 | flat の冗長・細分 | まつげ カール/パーマ/ボリューム… のよう同一語幹を細分大量出力 |
| P7 | namespace と flat の重複 | `種類/写真` と `写真` が同一画像で重複（プロンプト禁止あり、保存時 enforce なし） |

---

## 2. 確認した問題（データ証拠付き）

### P1 — ソース間結合ルール欠如（影響度: 中）

**P1a（保存）**: `filename` と `auto` が同一タグを別ソースに保存 — **意図通り**（§0 参照）。

**P1b（結合）**: 結合ロジックが重複を前提にしておらず、実害が出ている。

| タグ | 両ソースに存在する画像数 |
|---|---|
| 毛 / まんこ / パンツ | 630 / 586 / 565 |
| 乳首 / 制服 / チラ | 295 / 229 / 220 |
| うんこ / カス / 脚 / 腋 / メガネ | 200 / 190 / 163 / 137 / 135 |
| 透け / アナル / 修正 / 染み | 128 / 126 / 125 / 124 |

- 上記は `auto` と `filename` が同名タグを両方持つ画像数（§6 P1 クエリ）。
- **`effective_tags()` はソース間 dedup なし** — 同一 `(image_id, tag)` が `auto` と `filename` に両方あると、表示・検索・インデックスに**2 回出る**。
- 重複タグを 1 つ以上持つ画像は **2,220 枚**（under.iphone 3,926 の過半数）。

→ 問題の本質は、**`filename` を確定情報として結合時に優先する設計がなく**、VLM が `priority_tags` として渡されたタグを flat に再出力する構造（プロンプト上 `MUST appear in flat_tags`）と組み合わさって、**保存・表示の両方で冗長が増える**こと。結合時に「filename を確定・auto を補足・同値なら 1 件にまとめる」ルールが欠けている。

### P2 — 非公式 namespace 風タグ（影響度: 小〜中）

```
靴のNR/BRソール  靴のBR/CRソール  靴のNR/EPDMソール  靴のNR/SBRソール ...（8〜9種）
```

- `靴の` はパーサー由来ではなく **VLM が slash 付きで新規作成した疑似 namespace**（`under_iphone_legacy_v1.yaml` には不存在、`source=auto`、**flat タグとして保存**）。
- コードの `NAMESPACE_OPTIONS` は `種類/画角/アングル/人数` の4つのみ。`validate_namespace_tags()` は既知キーの**値の正当性**しか確認しない（未知キーは JSON から黙殺）。
- 影響は小規模（**18 画像**、タグ種 8〜9）だが、「namespace はこれだけ」とプロンプトが閉じていない証拠。

### P3 — ネスト規則の不一致（影響度: 中）

- `種類/文章/スクショ`（正しくネスト、10 件）と `文章/スクショ`（浮遊、5 件）が混在。
- 許可リスト上の正規形は `種類/` 配下。VLM の省略・誤ネストと思われる。
- 同一システム内で「いつネストするか」が規則化されていない。

### P4 — 同義 flat タグの共存（影響度: 大）

```
15389_2.png: セーラー服, セーラー襟
IMG2623_乳首-制服-透け.JPG ... セーラー服 ... セーラー襟 ...
```

- `セーラー服` と `セーラー襟` が**同一画像で両方保存**。両方を持つ画像は **73 画像**（§6 P4 クエリ）。
- 意味が近いタグを VLM が両方出力。`aliases` に `セーラー襟` → `セーラー服` が無く、VLM 出力にも `normalize_tags` が未適用。
- 注: 資料によっては意図的な粒度の可能性あり。alias 統合前にサンプル目視を推奨。

### P5 — flat タグ上限の未 enforce・外れ値（影響度: 中）

under.iphone の flat タグ数分布:

| flat数 | 画像数 |
|---|---|
| 1 | 23 |
| 10〜14 | 各120〜170（山） |
| 15〜25 | 各130〜180（ピーク） |
| 26〜60 | 減少傾向 |
| 61〜150 | 少数 |
| 最大 | **428**（`img_8d9793446bc22d75`、外れ値1画像） |

- flat 数の分布は **1〜428 と広範囲**。1 グは 23 画像と少なく、標準は 10〜25 前後で山をなる。
- **最大 428 グ**の画像が1存在。極端な外れ値。
- `max_flat_tags=60` はプロンプトに記載されるが、`vlm.py` の post-process に truncate が無く**未 enforce**。60 を遥かに超える出力が実際に発生。

### P6 — flat タグの冗長・細分（影響度: 中）

```
IMG4440: まつげ, まつげエクステ, まつげカーブ, まつげカール, まつげパーマ, まつげボリューム, まつげ光沢, まつげ太さ, まつげ密度, まつげ形状 ...（17個）
```

- 同一語幹（まつげ）を細分したタグを VLM が大量出力。
- 検索粒度として過剰な場合がある。ただし「まつげカール」で絞りたい需要もあり得る — 一律削除より語彙表での親語彙への畳み込みが現実的。

### P7 — namespace と flat の重複（影響度: 中）

```
IMG4585_パンツ-チラ.JPG: 種類/写真 + 写真
IMG5594_毛-パンツ.JPG:    種類/写真 + 写真
IMG6481_乳首-体操着-透け: 種類/写真 + 写真
```

- `種類/写真`（namespace）と `写真`（flat）が同一画像で重複（**51 画像**）。
- プロンプトには `Do not duplicate namespace_tags in flat_tags` があるが、**保存時・結合時の enforce が無い**。P1b と同種の冗長。

---

## 3. 根本原因（プロンプトと enforce の分離）

`src/siftivex/tag_vocabulary.py::build_system_prompt()` の指示と、コード側の enforce 状況:

| 指示（プロンプト） | enforce（コード） | 関連問題 |
|---|---|---|
| namespace 値は許可リストから選択 | `validate_namespace_tags()` で既知キーの値のみ検証 | P2（slash 付き flat は素通り） |
| flat は優先語彙 exact match | なし（VLM 出力に `normalize_tags` 未適用） | P4, P6 |
| priority_tags MUST appear in flat_tags | なし（再出力を**促す**側面あり） | P1b |
| Do not duplicate namespace in flat | なし | P7 |
| flat max {max_flat_tags} | **なし**（`vlm.py` に truncate 無し） | P5, P6 |
| ネスト規則 | なし | P3 |
| 同義タグの除外 | なし（`aliases` は filename 取込時のみ） | P4, P6 |

→ **核心は「プロンプトに書いてあるが、保存・結合ロジックで enforce していない」こと**。VLM 遵守に依存する設計では P1〜P7 が再発する。

---

## 4. 改善方向（検討方針）

> **設計方針の再考**: ルートごとに細かな優先ルールを定義するのはスマートではない。源ご事情（under.iphone の NSFW 多・pixiv のコミュニティタグ等）は異なり、個別調整が積み重なると汎用性が損なわれる。

本章の指摘は方向として正しいが、**完成した設計を一度に作るより、試行錯誤しながら形を作っていくべきもの**と位置づける。重点は「個別ルールの網羅」ではなく、システムの土台を固めること:

- **メタルール**: 源に依存しない一般規則（JSON 出力・重複時の振る舞い・命名規則など）を先に確定する。
- **優先タグの整理**: priority_tags の位置づけと、他ソースとの優先関係を洗練する。
- **namespace の洗練**: 許容リストを粛正し（P2）、ネスト規則を明確化（P3）する。

P1〜P7 はこの土台を固めるための**入力（確認材料）**であって、ゴールではない。実装は都度方針を決めながら進める。

**実装優先度の目安**: P5 enforce → `effective_tags` dedup（P1b/P7）→ VLM 出力への `normalize_tags` / alias → 語彙表拡充（P4/P6）。

### namespace の追加判定基準（決定済み）

namespace を追加するのは、次の **3 つの条件をすべて満たす軸**に限定する:

1. **値の集合が有限・明確**（閉じたリストにできる）
2. **源に依存しない**（under.iphone だけでなく pixiv・将来の源でも通用する）
3. **その軸でフィルタしたい需要がある**

この基準を満たさない軸（髪型・衣装など値が数百単位でぶれる）は namespace ではなく **flat + 語彙表で扱う**。

- **光の方向**（順光 / 逆光 / 側光 / 上光 / 下光）: 値は有限・源非依存・フィルタ需要あり → namespace 化の好候補。排他的なため**単一値**で、現行 4 つ（種類/画角/アングル/人数）と同設計。
- **光源・光の質**（蛍光灯 / 自然光 / やわらい光 / 硬い光…）: 複合して成立するため「光の方向」とは**別軸**。複数値対応が必要ならそれに合わせて設計。
- **重複可能性への対処**: 軸を分けて **プロンプトで明示**すればほぼ問題なし（同一 namespace に混ぜない）。これが P2（`靴の` 的発明）の再発防止にもなる。

---

## 5. 具体的方策（検討候補）

> 以下の各案は**検討中の候補**であり、そのまま採用しない。土台を固めながら試行錯誤で取捨選択する。源別・状況別の細かいルール網羅は意図しない。

### P1（ソース間結合）への案

- **← 対応問題：P1b（結合 dedup・優先順位）、P7（namespace/flat の重複）**
- `source` は既に `filename` / `auto` / `manual_added` / `manual_removed` がある。**rename より結合ルール追加**が変更は小さい。
- 結合ルール: `filename`（確定）と `auto`（提案）が同値なら **1 件にまとめる**。`effective_tags()` で `DISTINCT` または優先順位付き dedup。namespace と flat が同義（P7）も同様。
- VLM プロンプトの見直し: 現行 `MUST appear in flat_tags` は再出力を促す。`priority_tags` は「確認済み・再出力不要。新規タグのみ追加」と明示する方向を検討。
- 誤った確定タグ: 既存の `manual_removed` / `manual_added` 差分レイヤー（最優先）で修正。既存設計を流用。
- 注意: 確定タグが多い源では VLM の効きが鈍る可能性。源ごとの調整余地は残す（規定しない）。

### P2（非公式 namespace 風タグ）への案

- **← 対応問題：P2（許容リスト外の slash 付きタグ）**
- NAMESPACE_OPTIONS を階層（ツリー）で定義: `種類/{写真, イラスト, ...}` のように親-子を 1 つの構造で持つ。
- プロンプトにネスト完全リストを注入: 「値は下図のリストから。リスト外は出力禁止」。
- validate を再帰検証に改める: 親は NAMESPACE_OPTIONS のキーであること、子はその親の許容リストに属することをチェック。いずれも満たさなければ破棄（または flat へ降格）。
- post-process: flat 内の `foo/bar` 形式を検出し、許可リスト外なら破棄または flat 単語へ降格。これが `靴の` 系の回避策になる。

### P3（ネスト規則）への案

- **← 対応問題：P3（いつネストするか規則が無い）**
- ネスト判断基準を spec 化: 「子分類が別途定義される namespace のみネスト（種類/画角/アングル/人数）。子分類が無い場合は flat」。
- ネ可否を NAMESPACE_OPTIONS の構造で暗に表現: ネストする親のみ子リストを持つ構造に。子リストが無い親はネストしない、と自動で決まる。
- 「いつネストしないか」も規定: 扁平が適切なケース（単一分類など）を明示し、浮遊タグを抑制。

### P4（同義 flat タグ）への案

- **← 対応問題：P4（セーラー服 & セーラー襟 の同義共存）**
- 同義タグを `aliases`（語彙表）で統合。`セーラー襟` → `セーラー服` のように正規形へマージ。
- VLM 出力にも `normalize_tags` を適用（現状は filename 取込時のみ）。
- VLM には「同義のタグを同時に出力しない／正規形のみ出力」を指示。
- 統合前に P4 対象画像のサンプル目視で、意図的な粒度でないか確認。

### P5（flat の上限未 enforce・外れ値）への案

- **← 対応問題：P5（flat 数 1〜428、428 グの外れ値、上限未 enforce）**
- `vlm.py` post-process で `flat_tags[:max_flat_tags]` を enforce。プロンプトのみに依存しない。
- 下限は**源ごとの許容範囲としてパラメータ管理**（固定値にせず、下回った場合に補完指示）。
- 428 グ外れ値は上限適用で自動解消。

### P6（冗長・細分）への案

- **← 対応問題：P6（まつげカール/パーマ/… の細分大量出力）**
- 同一語幹の細分タグを**1語に集約**（まつげ系 → `まつげ`）。語彙表で「細分語彙 → 親語彙」のマッピングを保持。
- VLM には「細かな特徴は1語にまとめ、バリエーションを列挙しない」を指示。
- `max_flat_tags` enforce（P5）と連動。

### 補足: caption の扱い（要検討）

- under.iphone で caption 長分布: **0–10 字 4 枚**、**11–40 字 3,262 枚**、41+ 字 636 枚（§6 caption クエリ）。おおむね良質だが短過ぎが少数存在。
- **← 対応問題: caption の短過ぎ（品質保証）**。VLM に「1文で状況を記述」を追加指示することで対応可（要検証）。

---

## 6. 検証方法（再現）

```bash
cd ~/siftivex

# P1: クロス源重複（auto と filename が同名タグを両方持つ件数）
sqlite3 data/siftivex.db \
  "SELECT a.tag, COUNT(DISTINCT a.image_id) FROM image_tags a
   JOIN image_tags b ON a.image_id=b.image_id AND a.tag=b.tag AND b.source='filename'
   WHERE a.source='auto' GROUP BY a.tag ORDER BY 2 DESC LIMIT 15;"

# P1b: effective_tags 相当の重複（表示・検索に2回出る画像数）
sqlite3 data/siftivex.db \
  "SELECT COUNT(DISTINCT image_id) FROM (
     SELECT image_id, tag, COUNT(*) c FROM image_tags
     WHERE source IN ('auto','filename','manual_added')
     GROUP BY image_id, tag HAVING c > 1
   );"

# P2: 非公式 slash 付きタグ（flat に保存された疑似 namespace）
sqlite3 data/siftivex.db \
  "SELECT tag, COUNT(*) FROM image_tags
   WHERE source='auto' AND tag LIKE '%/%'
     AND substr(tag,1,instr(tag,'/')-1) NOT IN ('種類','アングル','人数','画角')
   GROUP BY tag ORDER BY 2 DESC;"

sqlite3 data/siftivex.db \
  "SELECT COUNT(DISTINCT image_id) FROM image_tags
   WHERE source='auto' AND tag LIKE '靴の%';"

# P3: ネスト不一致
sqlite3 data/siftivex.db \
  "SELECT tag, COUNT(*) FROM image_tags
   WHERE source='auto' AND (tag='種類/文章/スクショ' OR tag='文章/スクショ')
   GROUP BY tag;"

# P4: 同義共存（セーラー服 & セーラー襟）
sqlite3 data/siftivex.db \
  "SELECT COUNT(DISTINCT a.image_id) FROM image_tags a
   JOIN image_tags b ON a.image_id=b.image_id
   WHERE a.tag='セーラー服' AND b.tag='セーラー襟';"
# 実行結果: 73

# P5: flat 分布
sqlite3 data/siftivex.db \
  "SELECT COUNT(tag) AS c FROM image_tags
   WHERE source='auto' AND tag NOT LIKE '%/%'
   GROUP BY image_id;" \
  | awk '{print $1}' | sort -n | uniq -c | sort -k2 -n

# P7: namespace + flat 重複
sqlite3 data/siftivex.db \
  "SELECT COUNT(DISTINCT a.image_id) FROM image_tags a
   JOIN image_tags b ON a.image_id=b.image_id
   WHERE a.tag='種類/写真' AND b.tag='写真';"
# 実行結果: 51

# caption 長分布（under.iphone）
sqlite3 data/siftivex.db \
  "SELECT CASE
     WHEN length(vlm_caption) <= 10 THEN '0-10'
     WHEN length(vlm_caption) <= 40 THEN '11-40'
     ELSE '41+'
   END AS bucket, COUNT(*)
   FROM images
   WHERE route_tag='route/under-iphone' AND vlm_caption IS NOT NULL
   GROUP BY bucket;"
```

---

## 7. 出典ファイル

| 要素 | ファイル |
|---|---|
| タグ仕様 | `docs/specs/tags.md`（スケルトン） |
| システムプロンプト | `src/siftivex/tag_vocabulary.py` (`build_system_prompt`) |
| namespace 検証 | `src/siftivex/tag_vocabulary.py` (`validate_namespace_tags`) |
| タグ結合 | `src/siftivex/tags_db.py` (`effective_tags`) |
| under.iphone パーサー | `config/parsers/under_iphone_legacy_v1.yaml` |
| VLM クライアント | `src/siftivex/vlm.py` |

---

## 8. 実装反映状況（2026-09-07）

| 項目 | 状態 | 実装 |
|---|---|---|
| P5 flat 上限 enforce | ✅ | `process_vlm_tags()` → `vlm.py` で `max_flat_tags` truncate |
| P1b ソース間 dedup | ✅ | `effective_tags()` で `DISTINCT` |
| P7 namespace/flat dedup | ✅ | `dedupe_namespace_flat_tags()`（結合時 + VLM post-process） |
| P2 非公式 slash タグ | ✅ | `process_vlm_tags()` で許可外 slash タグを破棄 |
| P3 浮遊ネスト | ✅ | `文章/スクショ` 等を namespace へ promote |
| P4 alias | ✅ | `セーラー襟` → `セーラー服`（DEFAULT_ALIASES + yaml） |
| VLM 出力 normalize | ✅ | `process_vlm_tags()` で `normalize_tags` 適用 |
| priority_tags 再出力抑制 | ✅ | プロンプト変更 + auto flat から priority 除去 |
| P6 細分語彙畳み込み | 🔲 | 語彙表拡充は未着手（プロンプト指示のみ） |
| namespace 更新（光の方向/） | ✅ | `NAMESPACE_OPTIONS` + 動的 schema プロンプト |
| 既存 DB の一括修正 | 🔲 | 新規 VLM 実行・検索表示から効く。再タグは別途 |
