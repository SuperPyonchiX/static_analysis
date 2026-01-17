---
description: 'Static Analysis Auto-Classifier プロジェクトのPython開発ガイドライン。コーディング規約、型ヒント、エラーハンドリングの方針を定義。'
applyTo: '**/*.py'
---

# Python 開発ガイドライン

## 型ヒント

### 必須

全ての関数・メソッドに型ヒントを付与してください。

```python
# Good
def extract_function(file_path: str, line: int) -> Optional[FunctionInfo]:
    pass

# Bad
def extract_function(file_path, line):
    pass
```

### 複雑な型

`typing` モジュールを使用:

```python
from typing import List, Dict, Optional, Tuple, Callable

def find_callers(
    function_name: str,
    max_callers: int = 3
) -> List[FunctionInfo]:
    pass

def load_rules(config: Dict[str, Any]) -> Dict[str, RuleInfo]:
    pass
```

## データクラス

### 基本パターン

```python
from dataclasses import dataclass, field
from typing import Optional, List

@dataclass
class Finding:
    """静的解析の指摘情報。"""
    id: str
    location: SourceLocation
    rule_id: str
    message: str
    severity: Severity
    procedure: Optional[str] = None

    # 処理中に設定される追加情報
    function_code: Optional[str] = None
```

### デフォルト値にミュータブルオブジェクト

```python
# Good - field(default_factory=...) を使用
@dataclass
class AnalysisContext:
    caller_functions: List[FunctionInfo] = field(default_factory=list)

# Bad - 直接リストを指定しない
@dataclass
class AnalysisContext:
    caller_functions: List[FunctionInfo] = []  # 危険！
```

## エラーハンドリング

### 個別処理の失敗を許容

```python
# Good - 個別の失敗をログして続行
for finding in findings:
    try:
        result = classify_finding(finding)
        results[finding.id] = result
    except Exception as e:
        logger.warning(f"Failed to classify {finding.id}: {e}")
        results[finding.id] = create_error_result(finding.id, str(e))

# Bad - 1つの失敗で全体が停止
for finding in findings:
    result = classify_finding(finding)  # 例外で全体停止
```

### カスタム例外

```python
class ClangParseError(Exception):
    """Clangパースエラー。"""
    pass

class LLMError(Exception):
    """LLM API呼び出しエラー。"""
    pass
```

## ロギング

### 基本パターン

```python
import logging

logger = logging.getLogger(__name__)

def process_finding(finding: Finding) -> ClassificationResult:
    logger.debug(f"Processing {finding.id}: {finding.rule_id}")

    try:
        result = classify(finding)
        logger.info(f"Classified {finding.id}: {result.classification.value}")
        return result
    except Exception as e:
        logger.error(f"Failed to classify {finding.id}: {e}")
        raise
```

### ログレベル

- `DEBUG`: 詳細なトレース情報
- `INFO`: 進捗・完了報告
- `WARNING`: 回復可能なエラー、スキップ
- `ERROR`: 致命的でないエラー

## ドキュメント

### Google形式docstring

```python
def build_phase2_context(
    finding: Finding,
    phase1_context: AnalysisContext,
    max_callers: int = 2
) -> AnalysisContext:
    """Phase 2用のコンテキストを構築する。

    Phase 1で確信度が低かった場合に、追加のコンテキスト
    （呼び出し元、型定義、マクロ）を収集する。

    Args:
        finding: 対象の指摘情報
        phase1_context: Phase 1で構築したコンテキスト
        max_callers: 取得する呼び出し元の最大数

    Returns:
        追加コンテキストを含むAnalysisContext

    Raises:
        ClangParseError: ソースファイルのパースに失敗した場合
    """
```

## 非同期対応設計

将来のasyncio化を考慮:

```python
# 現在の同期版
def classify_finding(finding: Finding) -> ClassificationResult:
    context = build_context(finding)
    response = call_llm(context)
    return parse_response(response)

# 将来のasync版への移行が容易な設計
# - I/O処理を分離
# - 共有状態を最小化
# - 処理単位を独立させる
```

## インポート順序

```python
# 1. 標準ライブラリ
import os
import logging
from typing import List, Optional, Dict
from dataclasses import dataclass

# 2. サードパーティ
import pandas as pd
from pydantic import BaseModel
import clang.cindex as ci

# 3. ローカル
from .models import Finding, ClassificationResult
from .analyzer import ClangAnalyzer
```
