# Lambda Function Test Events

このディレクトリには、Lambda関数のテスト用イベントが含まれています。

## ファイル一覧

### `lambda-test-event.json`
CloudWatchアラームからSNS経由でLambda関数に送られるイベントのサンプルです。

## 使用方法

### 1. Lambdaコンソールでのテスト

1. **Lambdaコンソール** → `NotifyFunction` → **テスト** タブ
2. **新しいテストイベントを作成** をクリック
3. **テンプレート**: `sns` を選択
4. **イベント名**: `CloudWatchAlarmTest` (任意の名前)
5. **JSONエディタ**で `lambda-test-event.json` の内容をコピー&ペースト
6. **作成** ボタンをクリック
7. **テスト** ボタンでテスト実行

### 2. テストイベントの構造

```json
{
  "Records": [
    {
      "EventSource": "aws:sns",
      "Sns": {
        "Message": "{CloudWatchアラームの詳細情報}"
      }
    }
  ]
}
```

### 3. 重要なフィールド

#### SNS Message内のCloudWatchアラーム情報
- **AlarmName**: アラーム名
- **AlarmDescription**: アラームの説明
- **NewStateValue**: アラーム状態 ("ALARM", "OK", "INSUFFICIENT_DATA")
- **NewStateReason**: 状態変更の理由
- **StateChangeTime**: 状態変更時刻

### 4. カスタマイズ

環境に応じて以下を変更してください：

#### ARN情報
- **EventSubscriptionArn**: SNSサブスクリプションARN
- **TopicArn**: SNSトピックARN
- **AlarmArn**: CloudWatchアラームARN

#### アカウント情報
- **AWSAccountId**: AWSアカウントID
- **Region**: リージョン名

#### アラーム情報
- **AlarmName**: 実際のアラーム名
- **AlarmDescription**: 実際のアラーム説明

### 5. デバッグ用テスト手順

1. **デバッグ版Lambda関数**をデプロイ
2. **テストイベント**を実行
3. **CloudWatch Logs**で詳細ログを確認
4. **問題箇所**を特定
5. **修正後**に再テスト

### 6. 期待される結果

#### 正常な場合
- **ステータス**: 成功
- **レスポンス**: `{"statusCode": 200, "body": "..."}`
- **ログ**: 詳細な処理ログが出力
- **メール**: 通知メールが送信される

#### 問題がある場合
- **ステータス**: エラー
- **レスポンス**: `{"statusCode": 500, "body": "..."}`
- **ログ**: エラー詳細とスタックトレースが出力

## トラブルシューティング

### よくある問題

1. **環境変数未設定**
   - `EMAIL_SNS_TOPIC_ARN environment variable not set`
   - → Lambda関数の環境変数を確認

2. **権限不足**
   - `AccessDenied` エラー
   - → IAMロールの権限を確認

3. **SNSトピックARN間違い**
   - メール送信エラー
   - → 環境変数のARNを確認

4. **ロググループアクセスエラー**
   - ログ取得エラー
   - → IAMポリシーを確認

### ログ確認方法

1. **Lambda実行結果**でログ概要を確認
2. **CloudWatch Logs** (`/aws/lambda/NotifyFunction`) で詳細ログを確認
3. **エラー箇所**を特定して修正