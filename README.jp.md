# dd_suite — 他env間ディスパッチとパイプライン合成の組み合わせ: dd_*プロジェクトのコマンド1つから、専用env内での実行へ

独立した `dd_afpocket` / `dd_chembl` / `dd_confhunt` / `dd_docking` /
`dd_mdstability` / `dd_molview` / `dd_overlay` / `dd_prep` / `dd_seqalign`
の各レポジトリを、コードやenvを統合することなく**1つのsuite**として使える
ようにする薄いオーケストレーション層。各 `dd_*` プロジェクトは意図的に
専用の conda/mamba env を持ち続ける——依存関係の衝突を避けるためにあえて
分離してきた経緯があり（本稿執筆時点でも `rdkit` だけで env 間にバージョン
差がある: `dd_confhunt`=2025.09.6、`dd_docking`/`dd_mdstability`=2026.03.1、
残り5プロジェクトは2026.03.4）、そのため `dd_suite` はどのプロジェクトの
コードも直接importせず、どのenvとも共有しない。各プロジェクト自身の既存の
コンソールスクリプトCLIを、そのプロジェクト自身のenv内で呼び出すだけである。

- **ディスパッチ（`dd_suite`）**: `dd_suite <command> [args...]` は、
  dd_*プロジェクトの任意のコンソールスクリプト（`dd_prep-run`、
  `dd_docking-dock`、`dd_mdstability-run`など）を、そのプロジェクト自身の
  専用env内で、*どのシェルからでも*実行する——`conda activate`は一切不要。
  実行対象のenvは、コマンド名自体から直接導出される（dd_*のコンソール
  スクリプトはすべて`<project>-<verb>`、または`dd_confhunt`のような単一
  コマンドのプロジェクトでは`<project>`単体という命名規則を持ち、
  プロジェクト名自体にハイフンは含まれないため、最初の`-`で分割すれば
  env名が復元できる）。その後、`conda info --envs --json`（マシン/OSに
  依存しない——`/opt/miniforge3/...`のようなハードコードなし）で実際の
  env prefixへ解決し、絶対パスで実行する。出力はライブでストリームされる
  ため、各プロジェクト既存の`print(..., flush=True)`による進捗表示
  （`StepProgress`/`MDProgress`/`DockProgress`など）はそのままリアル
  タイムに表示され、実際の終了コードもそのまま返される。
- **パイプライン（`dd_suite-pipeline`）**: 複数のディスパッチ済みステージ
  を、すでに実在し手動でドキュメント化されているワークフローへと合成する。
  例えば`dock_and_validate`: `dd_mdstability-prep` -> `dd_docking-prep` ->
  `dd_docking-dock` -> `dd_mdstability-run`（`dd_mdstability/README.md`
  に載っている実例そのものを、手動4コマンドではなく1コマンドとして実行
  する）。汎用的なパイプラインDSL/設定形式ではなく、素直に合成された
  Python関数として実装している（`dd_suite/pipelines.py`）——今日時点で
  実在するパイプラインは1〜2個程度であり、各プロジェクトのCLIはすでに
  決定的でドキュメント化されたファイル名（`manifest.json`、
  `ranked_results.csv`、`<name>/report.json`など）へ出力しているため、
  パースやテンプレート化するものが何もない: `dd_suite`はユーザーが手で
  すでにタイプしているのと同じパスを組み立てているだけである。

## なぜ共有env・モノレポにしないのか

検討した上で却下した。各`dd_*`プロジェクトは、少なくとも1つのコア
パッケージについて異なるバージョン固定が必要である（具体的には`rdkit`だが、
プロジェクトによっては`openmm`やQt6なども）——1つの共有envに統一すると、
より古いバージョンに固定されたプロジェクトが壊れるか、他の全プロジェクトを
新しいバージョンに対して再検証する必要が生じる。`conda activate`ベースの
ラッパーも検討したが却下した: 非対話的シェル内でのenv activateは`PATH`
競合を確実に制することができない（このsuiteの他の場所ですでに一度踏んだ
既知の落とし穴）。そのため`dd_suite`が起動するすべてのサブプロセスは
`conda activate`ではなく**絶対パス**で解決・実行し、そのenvの`bin`/
`Scripts`ディレクトリをサブプロセス自身の`PATH`の先頭に追加する（一部の
dd_* CLI自体が、`PATH`上にあることを前提に別のコンソールスクリプトを
シェルアウトして呼んでいるため——例: `dd_docking-prep`がmeeko自身の
`mk_prepare_receptor.py`を呼び出すケース）。

## インストール

`dd_suite`自身は`rdkit`/`openmm`などの重い科学計算パッケージを一切import
しない——他のenvの既存CLIをシェルアウトするだけである——ため、自身のenvは
意図的に最小限にしてある:

```bash
mamba create -n dd_suite -c conda-forge python=3.12 pytest
conda activate dd_suite
cd dd_suite
pip install --no-deps -e .
```

これにより2つのコンソールコマンド、`dd_suite`、`dd_suite-pipeline`が
インストールされる。`dd_suite`がディスパッチする各`dd_*`プロジェクトは、
あらかじめ専用envがインストール済みである必要がある（env名 == プロジェクト
名、このsuite全体で確立された慣例）——`dd_suite`自身はそれらのenvを作成・
管理しない。

## 使い方

### ディスパッチ: どのenvからでもdd_*コマンドを実行

```bash
# dd_suite envから（あるいはどのenvからでもよい——dd_suite自体はactivate不要）
dd_suite dd_prep-run --help
dd_suite dd_docking-dock data/ensemble data/ligands.smi -o data/screen
dd_suite dd_mdstability-run data/raw/4EQC_raw.pdb data/screen/top_hits.sdf -o data/validate --platform CPU
```

これらはそれぞれ完全にその実行対象プロジェクト自身のenv（それぞれ
`dd_prep`、`dd_docking`、`dd_mdstability`）内で実行される——`dd_suite`
自体はそれらのコードにも依存関係にも一切触れない。

### パイプライン: dock_and_validate

`dd_mdstability/README.md`の実例そのものを1コマンドで実行する: 生の
共結晶PDBのポケットに対して`.smi`ライブラリをアンサンブルドッキングし、
最上位ヒットをMDで検証する。

```bash
dd_suite-pipeline dock_and_validate \
  data/raw/4EQC_raw.pdb XR1 data/ligands.smi \
  -o data/out/4eqc --platform CPU --screen-ns 0.25 --prod-ns 2.0
```

`<out_dir>/`以下の出力レイアウト: `prepped/`（ネイティブ参照リガンド、
`dd_mdstability-prep`経由）、`ensemble/manifest.json`（`dd_docking-prep`
経由）、`screen/ranked_results.csv` + `top_hits.sdf`（`dd_docking-dock`
経由）、`validate/<ligand_id>/report.json`（最上位ポーズに対する
`dd_mdstability-run`経由——最終的な安定性判定）。

### Python API

```python
from dd_suite import dock_and_validate

result = dock_and_validate(
    "data/raw/4EQC_raw.pdb", "XR1", "data/ligands.smi", "data/out/4eqc",
    platform="CPU", screen_ns=0.25, prod_ns=2.0,
)
print(result.report_json)  # -> data/out/4eqc/validate/<ligand_id>/report.json
```

## 新しいパイプラインの追加方法

1. 新しいステージ用の小さなアダプタ関数を`dd_suite/adapters.py`に追加する:
   そのCLI引数を組み立て、`dispatch.run(command, args)`を呼び、既知の
   出力パスを小さなデータクラスとして返す——パスの推測は不要、その
   プロジェクト自身のCLIがすでにドキュメント化しているファイル名を
   そのまま使うだけ。
2. `dd_suite/pipelines.py`にアダプタを合成した新しい関数を追加する。
3. `dd_suite/cli.py`の`main_pipeline`にサブコマンドとして公開する。

エンジン/DSLの変更は不要——これは`dd_mdstability.pipeline`/`dd_docking`
自身のCLIが、汎用フレームワークではなく小さな合成関数で構築されている
のと同じパターンである。

## モジュール構成（`dd_suite/`）

| ファイル | 役割 |
|---|---|
| `envs.py` | `<command>` -> 所属プロジェクト -> 実際のenv prefix（`conda info --envs --json`）-> 実際の実行ファイルパス（`shutil.which`）。`subprocess_env()`はディスパッチ先サブプロセスが実行される、`PATH`調整済みの環境を構築する |
| `dispatch.py` | `run(command, args)` -- 絶対パスで解決・実行、標準入出力はストリーム、実際の終了コードを返す |
| `adapters.py` | 連結可能なdd_* CLIステージごとの関数 + 結果データクラス |
| `pipelines.py` | 複数ステージを合成したワークフロー（現時点では`dock_and_validate`） |
| `cli.py` | `dd_suite`（Layer 1パススルー）/ `dd_suite-pipeline`（Layer 2サブコマンド） |

## 制限事項

- `dd_suite`は、ディスパッチ対象の各プロジェクトのenvがすでに存在し、
  プロジェクト名とまったく同じ名前である（`mamba create -n <project>
  ...`）ことを前提としている——それらのenvの作成・更新・管理は行わない。
- 現時点で実装済みのパイプラインは`dock_and_validate`の1つのみ。他の
  パイプライン（例: `dd_afpocket`を代替アンサンブルソースとして組み込む、
  `dd_chembl`のtrain -> predict -> dockループなど）も同じ方法で容易に
  追加できるが、まだ実装されていない。
