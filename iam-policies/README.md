# IAM Policies for CloudWatch Log Monitoring

このディレクトリには、CloudWatchログ監視システムで使用するIAMポリシーが含まれています。

## ファイル一覧

### `lambda-execution-policy.json`
Lambda関数の実行に必要な権限を定義したカスタムポリシーです。

#### 含まれる権限
1. **CloudWatch Logs権限**:
   - `logs:FilterLogEvents` - ログイベントのフィルタリング
   - `logs:GetLogEvents` - ログイベントの取得
   - `logs:DescribeLogStreams` - ログストリームの情報取得
   - `logs:DescribeLogGroups` - ロググループの情報取得
   - `logs:DescribeMetricFilters` - メトリクスフィルターの情報取得

2. **CloudWatch権限**:
   - `cloudwatch:DescribeAlarms` - アラーム情報の取得

3. **SNS権限**:
   - `sns:Publish` - 指定されたSNSトピックへのメッセージ発行

#### 適用方法

##### マネジメントコンソールでの適用
1. **IAMコンソール** → **ポリシー** → **ポリシーの作成**
2. **JSON** タブを選択
3. `lambda-execution-policy.json` の内容をコピー&ペースト
4. **ポリシー名**: `LogMonitoringPolicy` (または任意の名前)
5. **ポリシーの作成**
6. Lambda実行ロールにこのポリシーをアタッチ

##### AWS CLIでの適用
```bash
# ポリシーの作成
aws iam create-policy \
    --policy-name LogMonitoringPolicy \
    --policy-document file://iam-policies/lambda-execution-policy.json

# ロールへのアタッチ
aws iam attach-role-policy \
    --role-name <Lambda実行ロール名> \
    --policy-arn arn:aws:iam::<アカウントID>:policy/LogMonitoringPolicy
```

## 注意事項

### 環境固有の設定
以下の部分は環境に応じて変更してください：

- **SNSトピック名**: `LS-AWSLAB-ErrorNotificationEmail`
- **リージョン**: 必要に応じてARNのリージョン部分を調整
- **アカウントID**: 必要に応じてARNのアカウント部分を調整

### セキュリティ考慮事項

1. **最小権限の原則**: 必要最小限の権限のみを付与
2. **リソース制限**: SNS発行権限は特定のトピックのみに制限
3. **読み取り専用**: CloudWatch Logsは読み取り権限のみ

### 拡張性

このポリシーは以下の特徴があります：

- **すべてのロググループ対応**: `arn:aws:logs:*:*:log-group:*:*` により、新しいロググループ追加時にポリシー変更不要
- **将来対応**: 新しい監視対象を追加してもIAM設定の変更が不要

## 更新履歴

- **2025-01-08**: 初版作成
- **2025-01-08**: すべてのロググループに対応するよう更新（特定のロググループ指定から汎用的な設定に変更）