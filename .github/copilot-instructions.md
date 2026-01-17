# Static Analysis Auto-Classifier - Copilot Instructions

このプロジェクトは、車載組み込みC++ソフトウェアの静的解析結果を自動分類するPythonツールです。

## プロジェクト概要

- **目的**: CodeSonar/QACの静的解析指摘を「誤検知」「逸脱」「修正」に自動分類
- **対象**: AUTOSAR AP準拠、C++14、CERT C++/AUTOSAR C++14規約
- **技術**: Python 3.10+、libclang、Azure OpenAI API

## コーディング規約

### Python

- **型ヒント**: 全ての関数・メソッドに必須
- **データクラス**: `@dataclass` を積極的に使用
- **非同期対応**: 将来のasyncio化を考慮した設計
- **エラーハンドリング**: 個別処理の失敗が全体に影響しないよう設計

### 命名規則

- **クラス名**: PascalCase（例: `ClangAnalyzer`, `FunctionExtractor`）
- **関数名**: snake_case（例: `extract_function_at_line`）
- **定数**: UPPER_SNAKE_CASE（例: `MAX_INPUT_TOKENS`）
- **プライベート**: 先頭アンダースコア（例: `_cache_lock`）

### ドキュメント

- **docstring**: Google形式
- **コメント**: 日本語可（技術用語は英語のまま）
- **ログ**: `logging` モジュール使用、f-string形式

### 例

```python
from dataclasses import dataclass
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)

@dataclass
class FunctionInfo:
    """関数情報を保持するデータクラス。

    Attributes:
        name: 関数名
        file_path: ファイルパス
        start_line: 開始行（1始まり）
        end_line: 終了行（1始まり）
        code: 関数のソースコード
    """
    name: str
    file_path: str
    start_line: int
    end_line: int
    code: str
    signature: Optional[str] = None

def extract_function_at_line(
    file_path: str,
    line: int
) -> Optional[FunctionInfo]:
    """指定行を含む関数を抽出する。

    Args:
        file_path: ソースファイルパス
        line: 対象行番号（1始まり）

    Returns:
        FunctionInfo または None（関数が見つからない場合）
    """
    logger.debug(f"Extracting function at {file_path}:{line}")
    # 実装...
```

## ディレクトリ構造

- `src/models/`: データモデル（Finding, ClassificationResult等）
- `src/io/`: Excel入出力、ルールDB読み込み
- `src/analyzer/`: libclang使用のC++解析
- `src/classifier/`: Azure OpenAI API呼び出し
- `src/context/`: コンテキスト構築・最適化
- `src/utils/`: ロギング、リトライ等のユーティリティ
- `config/`: YAML設定ファイル、ルール定義

## 重要なクラス

- `StaticAnalysisClassifier`: メイン処理クラス
- `ClangAnalyzer`: libclangラッパー（TranslationUnitキャッシュ）
- `LLMClient`: Azure OpenAI API（構造化出力使用）
- `TokenOptimizer`: トークン上限最適化

## 静的解析ルール

このプロジェクトが扱う主なルール:

- **AUTOSAR C++14**: A0-1-1, A5-1-1, A7-1-1, A8-4-2 等
- **CERT C++**: DCL50-CPP, EXP50-CPP, MEM50-CPP 等

ルール情報は `config/rules/` のYAMLファイルに定義されています。

## テスト

- `pytest` 使用
- テストファイルは `tests/` ディレクトリ
- カバレッジ: `pytest --cov=src`
