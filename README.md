# Static Analysis Auto-Classifier

CodeSonar/QACなどの静的解析ツールの指摘を、Azure OpenAI (GPT) を使用して自動的に「誤検知」「逸脱」「修正」に分類するツールです。

## 概要

車載組み込みソフトウェア開発（AUTOSAR AP準拠、C++14）において、静的解析ツールの大量の指摘を効率的にトリアージするためのツールです。

### 主な機能

- **2段階判定フロー**: Phase 1で関数コードのみ、確信度が低い場合はPhase 2で呼び出し元・型定義を追加
- **libclang使用**: 高精度なC++コード解析（関数抽出、呼び出し元追跡）
- **ルールDB対応**: 組織の既存ルールDB（Excel/CSV）を読み込み可能
- **Excel出力**: 入力ファイルに分類結果を色分け表示で追記

### 分類カテゴリ

| 分類 | 説明 |
|------|------|
| 誤検知 | 静的解析ツールの誤検知。コードは規約に準拠している |
| 逸脱 | 意図的な規約からの逸脱。正当な技術的理由がある |
| 修正 | 実際に修正が必要な問題 |

## クイックスタート

### 1. 環境変数設定

```bash
# Windows
set AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
set AZURE_OPENAI_API_KEY=your-api-key

# Linux/macOS
export AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
export AZURE_OPENAI_API_KEY=your-api-key
```

### 2. インストール

```bash
# リポジトリをクローン
git clone https://github.com/your-org/static-analysis-classifier.git
cd static-analysis-classifier

# 依存関係をインストール
pip install -r requirements.txt
```

### 3. 設定ファイルを編集

`config/default_config.yaml` を編集し、以下を設定:

```yaml
# インクルードパス（C++解析用）
include_paths:
  - "C:/your-project/include"
  - "C:/your-project/src"

# ソースディレクトリ（呼び出し元検索用）
source_directories:
  - "C:/your-project/src"

# ルールDB（オプション）
rules_source:
  type: "excel"
  path: "C:/your-rules/autosar_rules.xlsx"
```

### 4. 実行

```bash
python -m src.main -i codesonar_report.xlsx -o classified_report.xlsx
```

## 入力形式

CodeSonar形式のExcelファイル。以下の列が必要です:

| 列名 | 必須 | 説明 |
|------|------|------|
| File | ○ | ソースファイルパス |
| Line | ○ | 行番号 |
| Rule | ○ | ルールID（例: A5-1-1, DCL50-CPP） |
| Message | ○ | 指摘メッセージ |
| Severity/Priority | | 重大度 |
| Procedure/Function | | 関数名 |

## 出力形式

入力Excelに以下の列を追加:

| 列名 | 説明 |
|------|------|
| 分類 | 誤検知/逸脱/修正（色分け表示） |
| 分類理由 | 分類の詳細な理由（日本語） |
| 確信度 | 判定の確信度（0-100%） |
| 判定フェーズ | Phase 1 または Phase 2 |

また、Summaryシートに統計情報を追加します。

## 設定ファイル

### config/default_config.yaml

```yaml
# Azure OpenAI設定
azure_api_version: "2024-10-21"
deployment_name: "gpt-5-mini"

# C++解析設定
include_paths:
  - "C:/project/include"
source_directories:
  - "C:/project/src"
compiler_args:
  - "-DAUTOSAR_AP"

# 処理設定
confidence_threshold: 0.8  # Phase 2移行の閾値
request_delay: 1.0         # API呼び出し間隔（秒）

# ルールDB設定
rules_source:
  type: "yaml"  # yaml / excel / csv
  path: "config/rules/autosar_cpp14.yaml"
```

### ルールDB形式

#### YAML形式

```yaml
rules:
  A5-1-1:
    title: "Literal values shall not be used..."
    category: "Required"
    rationale: "マジックナンバーは可読性を低下させる"
    false_positive_hints:
      - "0, 1 などの自明な値"
      - "型初期化での使用"
```

#### Excel/CSV形式

| Rule ID | Title | Category | Rationale | False Positive Hints |
|---------|-------|----------|-----------|---------------------|
| A5-1-1 | Literal values... | Required | マジック... | 0, 1などの自明な値; ... |

## アーキテクチャ

```
static_analysis/
├── src/
│   ├── main.py                 # エントリーポイント
│   ├── config.py               # 設定管理
│   ├── models/                 # データモデル
│   ├── io/                     # Excel入出力
│   ├── analyzer/               # C++解析（libclang）
│   ├── classifier/             # LLM分類
│   ├── context/                # コンテキスト管理
│   └── utils/                  # ユーティリティ
├── config/
│   ├── default_config.yaml
│   └── rules/                  # ルール定義
└── tests/
```

### 処理フロー

```
┌─────────────────────────────────────────────────────────────┐
│                        Phase 1                              │
│  Excel読込 → 関数抽出(libclang) → LLM判定 → 確信度チェック  │
└─────────────────────────────────────────────────────────────┘
                              ↓ 確信度 < 0.8
┌─────────────────────────────────────────────────────────────┐
│                        Phase 2                              │
│  呼び出し元追加 → 型定義追加 → マクロ追加 → LLM再判定       │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                        出力                                 │
│  Excel書き込み（分類結果追記） → Summaryシート追加          │
└─────────────────────────────────────────────────────────────┘
```

## コマンドラインオプション

```bash
python -m src.main [オプション]

必須:
  -i, --input   入力Excelファイル（CodeSonarレポート）
  -o, --output  出力Excelファイル

オプション:
  -c, --config  設定ファイルパス（デフォルト: config/default_config.yaml）
  -s, --sheet   処理するシート名
  -v, --verbose 詳細ログを出力
```

## 開発

### 開発環境セットアップ

```bash
# 仮想環境作成
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 開発用依存関係インストール
pip install -r requirements.txt

# libclang動作確認
python -c "import clang.cindex; print('libclang OK')"
```

### テスト実行

```bash
# 全テスト実行
pytest

# カバレッジ付き
pytest --cov=src
```

## 必要な環境

- Python 3.10以上
- Windows / Linux / macOS
- Azure OpenAI APIアクセス（GPT-5-mini推奨）

### 依存ライブラリ

- pandas, openpyxl: Excel処理
- libclang: C++解析
- openai, pydantic: Azure OpenAI API
- pyyaml: 設定ファイル

## ライセンス

MIT License

## 貢献

Issue報告やPull Requestを歓迎します。
