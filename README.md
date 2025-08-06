# AWS CloudWatch Log Monitoring System

AWS CDKを使用したCloudWatchログ監視システムです。EC2インスタンスのログを監視し、エラーが発生した際にメール通知を行います。

## システム概要

このシステムは以下の機能を提供します：

- **ログ監視**: EC2インスタンス（MTA01）の複数のログソースを監視
- **エラー検出**: 設定されたパターンに基づいてエラーを自動検出
- **アラート通知**: CloudWatchアラームによる即座の通知
- **詳細レポート**: エラー発生時の詳細なログ情報をメールで送信

## アーキテクチャ

```
CloudWatch Logs → Metric Filters → CloudWatch Alarms → SNS → Lambda → SNS → Email
```

### 主要コンポーネント

1. **CloudWatch Logs**: ログの収集と保存
2. **Metric Filters**: エラーパターンの検出
3. **CloudWatch Alarms**: 閾値ベースのアラート
4. **SNS Topics**: 通知の配信
5. **Lambda Function**: ログ解析と通知内容の生成

## 監視対象

現在、以下のロググループを監視しています：

- `LS-AWSLAB-EC2-MTA01-Log-messages` (システムメッセージログ)
  - フィルターパターン: `[error]`
- `LS-AWSLAB-EC2-MTA01-Log-app` (アプリケーションログ)
  - フィルターパターン: `ERROR`

## セットアップ

### 前提条件

- Python 3.8以上
- AWS CLI設定済み
- AWS CDK CLI (`npm install -g aws-cdk`)

### インストール

1. リポジトリをクローン
```bash
git clone <repository-url>
cd monitoring-system
```

2. 仮想環境の作成と有効化
```bash
cd monitoring_cdk
python3 -m venv .venv
source .venv/bin/activate  # Linux/Mac
# または
.venv\Scripts\activate.bat  # Windows
```

3. 依存関係のインストール
```bash
pip install -r requirements.txt
```

### デプロイ

1. CDKのブートストラップ（初回のみ）
```bash
cdk bootstrap
```

2. スタックのデプロイ
```bash
cdk deploy
```

## 設定

### メール通知先の変更

`monitoring_cdk/monitoring_cdk_stack.py`の以下の行を編集：

```python
self.email_notification_topic.add_subscription(
    subs.EmailSubscription("your-email@example.com")
)
```

### 監視対象ログの追加

`monitoring_cdk_stack.py`の`log_groups_config`配列に新しい設定を追加：

```python
{
    "name": "新しいロググループ名",
    "display_name": "表示名",
    "filter_pattern": "エラーパターン",
    "description": "説明"
}
```

## テスト

統合テストの実行：

```bash
python tmp_rovodev_integration_test.py
```

## ディレクトリ構造

```
monitoring_cdk/
├── app.py                          # CDKアプリケーションのエントリーポイント
├── monitoring_cdk/
│   └── monitoring_cdk_stack.py     # メインのCDKスタック定義
├── lambda/
│   ├── notify.py                   # Lambda関数のコード
│   ├── Dockerfile                  # Lambda用Dockerイメージ
│   └── requirements.txt            # Lambda依存関係
├── tests/
│   └── unit/
│       └── test_monitoring_cdk_stack.py
├── requirements.txt                # CDK依存関係
└── cdk.json                       # CDK設定
```

## 運用

### ログの確認

CloudWatch Logsコンソールで以下を確認：
- Lambda関数の実行ログ
- 監視対象ログの内容

### アラームの状態確認

CloudWatchアラームコンソールで各アラームの状態を確認

### メトリクスの確認

CloudWatchメトリクスコンソールで以下の名前空間を確認：
- `LS-AWSLAB-ErrorMonitoring`
- `LS-AWSLAB-EC2-MTA01`

## トラブルシューティング

### よくある問題

1. **Lambda関数がタイムアウトする**
   - `monitoring_cdk_stack.py`でタイムアウト値を調整

2. **メール通知が届かない**
   - SNSサブスクリプションの確認が必要
   - スパムフォルダを確認

3. **アラームが発火しない**
   - メトリクスフィルターの設定を確認
   - ログの形式とフィルターパターンの一致を確認

## ライセンス

このプロジェクトはMITライセンスの下で公開されています。

## 貢献

プルリクエストや課題報告を歓迎します。