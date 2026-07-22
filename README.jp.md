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
名、このsuite全体で確立された慣例）——以下は、それらすべてを一括で
インストールする方法である。

## dd_*プロジェクトを一括インストールする

各プロジェクト自身のREADMEに、そのプロジェクト固有の`mamba create -n
<project> ...` + `pip install --no-deps -e .`という正確なレシピが
ドキュメント化されている（パッケージリストはプロジェクトごとに異なり、
すべてに共通する万能envは存在しない）。`scripts/install_all.py`は、この
10個すべてを再生する——何も新しく発明はしていない、単なる自動化である:

```bash
python3 scripts/install_all.py            # 全プロジェクト、既存envはスキップ
python3 scripts/install_all.py --only dd_prep dd_docking   # この2つだけ
python3 scripts/install_all.py --dry-run   # 実行せず、すべてのコマンドを表示するだけ
python3 scripts/install_all.py --force     # 既存envを削除して再作成（破壊的）
```

標準ライブラリのみで動作するため、`dd_suite`自体がインストールされる前
でも任意のPython 3.9以降で実行できる——各プロジェクトが`dd_suite`の
兄弟ディレクトリとして存在すること（`~/work/<project>`、このsuiteで
確立されたレイアウト）を前提としている。

**`dd_molview`と`dd_overlay`はネイティブC++ビルドを伴う**——`dd_suite`が
自動化するのは通常のconda/pip部分のみであり、C++ツールチェーンに関わる
部分は自動化していない。下の表だけに頼らず、インストール前に必ず該当
プロジェクト自身のREADMEを読むこと:
- **`dd_molview`** はpipパッケージではなく、コンパイル済みのC++/Qt6
  アプリケーションである——`install_all.py`が自動化するのはenv作成のみ
  で、実際の`cmake -S . -B build && cmake --build build`ステップ
  （CMake ≥3.21、C++20コンパイラ、WebEngineWidgets込みの完全なQt6が
  必要）は手動である。OSごとのコンパイラ/Qt6セットアップとトラブル
  シューティングについては`dd_molview/README.md`の「Installation」節を
  参照すること。**Intel Mac（`osx-64`）は非対応**——conda-forgeがそのプラット
  フォーム向けの`qt6-webengine`ビルドを提供していないため（`osx-arm64`、
  `linux-64`、`win-64`のみ存在）、`install_all.py`は`osx-64`を検知すると
  実行全体を失敗させる代わりに`dd_molview`のenv作成を自動的にスキップする。
  Intel Macでの回避策（Homebrewベースのビルド）については
  `dd_molview/README.md`の「Installation」節を参照すること。
- **`dd_overlay`** は通常の`pip install --no-deps --no-build-isolation
  -e .`の一部として*オプションの*`pybind11`ネイティブアクセラレータを
  ビルドする——C++コンパイラが無ければ黙って純Python実装にフォール
  バックするため、いずれの場合もインストール自体は成功するが、実際に
  高速パスがビルドされたかどうかは`install_all.py`の出力からは分から
  ない。OSごとのコンパイラ前提条件と、実際にビルドされたかを確認する
  1行チェック（`optimize._HAVE_NATIVE`）については`dd_overlay/README.md`
  の「Native acceleration」節を参照すること。

| プロジェクト | envパッケージ（conda-forge） | 備考 |
|---|---|---|
| `dd_prep` | `rdkit numpy openmm pdbfixer` | |
| `dd_afpocket` | `rdkit numpy pandas pdbfixer openmm mdtraj matplotlib scipy scikit-learn py3dmol pytest fpocket` | `fpocket`は外部CLIバイナリ |
| `dd_chembl` | `rdkit lightgbm scikit-learn joblib` | |
| `dd_confhunt` | `"rdkit<2026" dimorphite-dl numpy` | `<2026`に固定——`dimorphite-dl`自体がそれを要求する |
| `dd_docking` | `rdkit numpy pandas qvina meeko pdbfixer openmm openmmforcefields openff-toolkit mdtraj` | `qvina`は外部CLIバイナリ（QuickVina2） |
| `dd_mdstability` | `rdkit numpy pandas matplotlib pdbfixer openmm openmmforcefields openff-toolkit mdtraj pytest` | |
| `dd_overlay` | `rdkit numpy scipy py3dmol pytest pybind11` | `pybind11`はオプションのネイティブアクセラレータをビルドする。`--no-build-isolation`付きでインストール |
| `dd_seqalign` | `biopython pandas numpy matplotlib py3dmol streamlit pymol-open-source fpocket rdkit` | `fpocket`は外部CLIバイナリ |
| `dd_molview` | `rdkit biopython pandas numpy py3dmol pybind11 pytest qt6-main qt6-webengine` | C++/Qt6ビルド——env作成は自動化されているが、`cmake -S . -B build && cmake --build build`ステップは自動化されていない（`dd_molview/README.md`参照）。**Intel Mac（`osx-64`）は非対応**——conda-forgeに同プラットフォーム向けの`qt6-webengine`が無いため`install_all.py`が自動スキップする |
| `dd_suite` | `pytest` | 本プロジェクト |

全プロジェクトの処理が終わると、`install_all.py`は`install_manifest.json`
（gitignore対象——マシン固有のスナップショットであり、コミットするもの
ではない）を書き出し、実際に何がどこにインストールされたかのサマリー
テーブルを表示する:

```
=== install summary ===
project          version    commit    status
dd_prep          0.1.0      07b0b41   ok
dd_afpocket      0.1.0      35b6226   ok
...
dd_molview       -          aa7aa36   env-only (manual cmake build required)
dd_suite         0.1.0      ebb13ec   ok
```

これは**現在インストールされているものの記録**であり、ロックファイル/
バージョン固定の仕組みではない——`version`は各プロジェクト自身の
`pyproject.toml`のバージョン（`pip show`）、`commit`はそのレポジトリの
現在のgitコミットであり、各プロジェクトのどのコミットが実際にそのenv
で動いているかが一目でわかる。`dd_*`プロジェクトはまだどれも正式な
リリースタグを持っていないため、「特定のバージョン/タグへ固定して
インストールする」（「今チェックアウトされているコミットをそのまま
使う」ではなく）仕組みはまだ用意していない——タグ運用が始まったら
見直す価値がある。

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
| `scripts/install_all.py` | 10プロジェクト全部のenvを一括構築するスタンドアロンインストーラー（前述の「dd_*プロジェクトを一括インストールする」参照）——`dd_suite`パッケージ自体には含まれない、標準ライブラリのみのスクリプト |

## 制限事項

- `dd_suite`（`dd_suite`/`dd_suite-pipeline`コマンド）は、ディスパッチ
  対象の各プロジェクトのenvがすでに存在し、プロジェクト名とまったく
  同じ名前であることを前提としている——それらのenvの作成・更新・管理は
  自身では行わない。`scripts/install_all.py`はそのための別建ての
  スタンドアロンなブートストラップスクリプトである（前述参照）——
  ディスパッチャ/パイプラインのコード自体はこれを呼び出さない。
- `install_all.py`は10プロジェクト中9つについてenv作成+editable
  インストールを自動化する。`dd_molview`のC++/Qt6ビルドステップは
  自動化されていない（env作成は自動化されている）——詳細は同プロジェクト
  自身のREADME参照。
- `install_manifest.json`は「何がインストールされているか」（バージョン+
  gitコミット）を記録するものであり、「何をインストールすべきか」を
  固定するロックファイルではない——`dd_*`プロジェクトはまだどれも正式な
  リリースタグを持っていないため、「dd_prepのv1.2.3を厳密にインストール
  する」というモードはまだない。
- 現時点で実装済みのパイプラインは`dock_and_validate`の1つのみ。他の
  パイプライン（例: `dd_afpocket`を代替アンサンブルソースとして組み込む、
  `dd_chembl`のtrain -> predict -> dockループなど）も同じ方法で容易に
  追加できるが、まだ実装されていない。
