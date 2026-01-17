# プロジェクト名

プロジェクトの概要を1-2文で簡潔に記述。

## プロジェクト構成

このプロジェクトの全体構造と主要なディレクトリ:

```
project-root/
├── src/              # ソースコード
│   ├── components/   # UIコンポーネント
│   ├── services/     # ビジネスロジック
│   └── utils/        # ユーティリティ関数
├── tests/            # テストコード
├── docs/             # ドキュメント
├── .github/          # GitHub設定
│   ├── workflows/    # CI/CDワークフロー
│   └── instructions/ # コーディング規約
└── config/           # 設定ファイル
```

## 技術スタック

### フロントエンド
- **フレームワーク**: React 18.x / Vue 3.x / Angular 17.x
- **言語**: TypeScript 5.x
- **スタイリング**: Tailwind CSS / CSS Modules / Styled Components
- **状態管理**: Redux Toolkit / Zustand / Pinia

### バックエンド
- **ランタイム**: Node.js 20.x LTS
- **フレームワーク**: Express 4.x / Fastify 4.x / NestJS 10.x
- **言語**: TypeScript 5.x
- **データベース**: PostgreSQL 16.x / MongoDB 7.x
- **ORM**: Prisma 5.x / TypeORM 0.3.x

### 開発ツール
- **パッケージマネージャー**: npm / yarn / pnpm
- **ビルドツール**: Vite 5.x / Webpack 5.x / Turbopack
- **リンター**: ESLint 8.x
- **フォーマッター**: Prettier 3.x
- **テストフレームワーク**: Jest 29.x / Vitest 1.x

## 前提条件

### 開発環境
- **Node.js**: 20.x LTS以上
- **パッケージマネージャー**: pnpm 8.x（推奨）
- **エディタ**: VS Code（推奨）
- **OS**: Windows 11 / macOS 14.x / Ubuntu 22.04 LTS

### 必須ツール
```bash
# Node.jsバージョン確認
node --version  # v20.x.x

# pnpmインストール（未インストールの場合）
npm install -g pnpm

# VS Code拡張機能（推奨）
# - ESLint
# - Prettier
# - GitHub Copilot
# - TypeScript and JavaScript Language Features
```

### 環境変数
プロジェクトルートに `.env` ファイルを作成:

```env
# データベース接続
DATABASE_URL="postgresql://user:password@localhost:5432/dbname"

# API設定
API_BASE_URL="http://localhost:3000"
API_KEY="your-api-key"

# 認証
JWT_SECRET="your-secret-key"
JWT_EXPIRES_IN="7d"

# 外部サービス
STRIPE_SECRET_KEY="sk_test_..."
SENDGRID_API_KEY="SG...."
```

## アーキテクチャ

### 全体設計
- **アーキテクチャパターン**: クリーンアーキテクチャ / レイヤードアーキテクチャ
- **設計原則**: SOLID原則、DRY、KISS
- **コード構成**: 機能ベース（Feature-based）/ ドメイン駆動設計（DDD）

### ディレクトリ構造の原則
- `src/components/`: 再利用可能なUIコンポーネント（プレゼンテーション層）
- `src/features/`: 機能ごとのモジュール（ビジネスロジック層）
- `src/services/`: 外部API連携、データアクセス層
- `src/utils/`: 共通ユーティリティ、ヘルパー関数
- `src/types/`: TypeScript型定義
- `src/hooks/`: カスタムReact Hooks（フロントエンドの場合）
- `src/stores/`: 状態管理ストア

### データフロー
```
User Input → Component → Hook/Service → API → Database
          ← Component ← State Update ← Response ←
```

## ビルド・デプロイ

### ビルドプロセス
```bash
# 本番用ビルド
pnpm build

# ビルド成果物確認
ls -la dist/
```

### デプロイ環境
- **開発環境**: `develop`ブランチへのマージで自動デプロイ
- **ステージング環境**: `staging`ブランチへのマージで自動デプロイ
- **本番環境**: `main`ブランチへのマージで自動デプロイ

### CI/CD
- **CI**: GitHub Actions（`.github/workflows/ci.yml`）
- **CD**: GitHub Actions（`.github/workflows/deploy.yml`）
- **自動テスト**: PRごとに実行
- **自動デプロイ**: マージ後に実行

## 追加リソース

- [プロジェクトWiki](https://github.com/your-org/your-project/wiki)
- [API ドキュメント](https://api-docs.example.com)
- [デザインシステム](https://design.example.com)
- [Slack チャンネル](https://your-team.slack.com/archives/C123456)

