# Static Analysis Auto-Classifier

車載組み込みC++ソフトウェアの静的解析結果を、Azure OpenAI APIを使用して自動分類するPythonツール。

## プロジェクト構成

```
static_analysis/
├── src/
│   ├── main.py                    # エントリーポイント・StaticAnalysisClassifierクラス
│   ├── config.py                  # Config dataclass・YAML読み込み
│   ├── models/                    # データモデル
│   │   ├── finding.py             # Finding, SourceLocation, Severity
│   │   ├── classification.py      # ClassificationResult, ClassificationType
│   │   └── context.py             # AnalysisContext, FunctionInfo, RuleInfo
│   ├── io/                        # Excel入出力
│   │   ├── excel_reader.py        # ExcelReader - CodeSonar形式対応
│   │   ├── excel_writer.py        # ExcelWriter - 色分け・Summary追加
│   │   └── rules_loader.py        # RulesLoader - YAML/Excel/CSV対応
│   ├── analyzer/                  # C++解析（libclang使用）
│   │   ├── clang_analyzer.py      # ClangAnalyzer - TranslationUnit管理
│   │   ├── function_extractor.py  # FunctionExtractor - 関数抽出
│   │   ├── caller_tracker.py      # CallerTracker - 呼び出し元追跡
│   │   └── symbol_resolver.py     # SymbolResolver - 型・マクロ解決
│   ├── classifier/                # LLM分類
│   │   ├── llm_client.py          # LLMClient - Azure OpenAI呼び出し
│   │   ├── prompt_builder.py      # PromptBuilder - Phase1/2プロンプト構築
│   │   └── response_parser.py     # ResponseParser - JSON→ClassificationResult
│   ├── context/                   # コンテキスト管理
│   │   ├── context_builder.py     # ContextBuilder - Phase1/2コンテキスト構築
│   │   └── token_optimizer.py     # TokenOptimizer - トークン上限最適化
│   └── utils/
│       ├── logger.py              # ロギング設定
│       └── retry.py               # リトライデコレータ
├── config/
│   ├── default_config.yaml        # デフォルト設定
│   └── rules/
│       ├── autosar_cpp14.yaml     # AUTOSAR C++14ルール定義
│       └── cert_cpp.yaml          # CERT C++ルール定義
├── tests/                         # pytestテスト
├── requirements.txt
├── README.md
└── CLAUDE.md                      # このファイル
```

## 技術スタック

### 言語・ランタイム
- **Python**: 3.10以上
- **対象言語**: C++14（AUTOSAR AP準拠）

### 主要ライブラリ
- **libclang** (>=18.1.1): C++ソースコードのAST解析
- **openai** (>=1.42.0): Azure OpenAI API（構造化出力対応）
- **pydantic** (>=2.8.0): データバリデーション・構造化出力スキーマ
- **pandas** (>=2.0.0): Excel読み込み
- **openpyxl** (>=3.1.0): Excel書き込み
- **pyyaml** (>=6.0): 設定ファイル

### 外部サービス
- **Azure OpenAI API**: GPT-5-mini（構造化出力対応）

## 前提条件

### 必須
- Python 3.10以上
- Azure OpenAI APIアクセス

### 環境変数
```bash
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-api-key
```

### libclang
- `pip install libclang` でWindows/Linux/macOS対応
- 追加のLLVMインストールは通常不要

## アーキテクチャ

### 設計原則
- **モジュラー設計**: 各コンポーネントが独立して動作
- **将来の並列化対応**: asyncio化を考慮した設計
- **エラー耐性**: 個別指摘の処理失敗が全体に影響しない

### データフロー
```
Excel → ExcelReader → Finding[]
                         ↓
Finding → ContextBuilder → AnalysisContext
                              ↓
                    PromptBuilder → Prompt
                              ↓
                    LLMClient → ClassificationResponse
                              ↓
                    ResponseParser → ClassificationResult
                              ↓
ClassificationResult[] → ExcelWriter → Excel
```

### 2段階判定フロー
1. **Phase 1**: 対象関数コードのみでLLM判定
   - 確信度 >= 0.8 → 結果確定
   - 確信度 < 0.8 → Phase 2へ

2. **Phase 2**: 追加コンテキスト付きで再判定
   - 呼び出し元関数（最大2件）
   - 関連型定義（最大5件）
   - 関連マクロ（最大5件）

## ビルド・実行

### インストール
```bash
pip install -r requirements.txt
```

### 実行
```bash
python -m src.main -i input.xlsx -o output.xlsx -c config/default_config.yaml
```

### テスト
```bash
pytest
pytest --cov=src
```

## 主要クラス

### StaticAnalysisClassifier (src/main.py)
メイン処理クラス。全コンポーネントを統合。

### ClangAnalyzer (src/analyzer/clang_analyzer.py)
libclangラッパー。TranslationUnitのキャッシュ管理。

### LLMClient (src/classifier/llm_client.py)
Azure OpenAI API呼び出し。Pydantic構造化出力使用。

### TokenOptimizer (src/context/token_optimizer.py)
GPT-5-miniのトークン上限（250,000）内に収める最適化。

## コーディング規約

- 型ヒント必須
- dataclass使用推奨
- ロギングはloggingモジュール使用
- 日本語コメント可
- docstringはGoogle形式
