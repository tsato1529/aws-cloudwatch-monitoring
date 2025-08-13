# Lambda Function Debug Test Codes

Lambda関数のデバッグ用段階的テストコードです。問題の原因を特定するために、機能を段階的に追加してテストします。

## テスト手順

### Step 1: 最小限のテスト (`step1-minimal-test.py`)

**目的**: Lambda関数の基本動作確認

**含まれる機能**:
- 基本的なイベント受信
- JSON処理
- ログ出力

**期待される結果**:
```
START RequestId: xxx
=== MINIMAL TEST STARTED ===
Event received: {...}
=== MINIMAL TEST COMPLETED ===
END RequestId: xxx
REPORT RequestId: xxx Duration: 100.00 ms
```

**使用方法**:
1. `step1-minimal-test.py` の内容をLambda関数にコピー
2. Deploy → Test実行
3. ログを確認

---

### Step 2: 環境変数テスト (`step2-environment-variables-test.py`)

**目的**: 環境変数の読み取り確認

**追加機能**:
- `os` モジュール
- 環境変数の取得

**期待される結果**:
```
START RequestId: xxx
=== TEST WITH ENVIRONMENT VARIABLES ===
Event received: {...}
EMAIL_SNS_TOPIC_ARN: arn:aws:sns:...
=== TEST COMPLETED ===
END RequestId: xxx
```

**確認ポイント**:
- 環境変数が正しく取得できているか
- `EMAIL_SNS_TOPIC_ARN` の値が正しいか

---

### Step 3: boto3テスト (`step3-boto3-test.py`)

**目的**: AWS SDK (boto3) の動作確認

**追加機能**:
- `boto3` モジュール
- SNSクライアント作成
- CloudWatch Logsクライアント作成

**期待される結果**:
```
START RequestId: xxx
=== TEST WITH BOTO3 ===
Event received: {...}
EMAIL_SNS_TOPIC_ARN: arn:aws:sns:...
boto3 SNS client created successfully
boto3 CloudWatch Logs client created successfully
=== TEST COMPLETED ===
END RequestId: xxx
```

**確認ポイント**:
- boto3クライアントが正常に作成できるか
- IAM権限が正しく設定されているか

---

### Step 4: 全インポートテスト (`step4-imports-test.py`)

**目的**: 本番コードで使用するすべてのモジュールの動作確認

**追加機能**:
- `re` モジュール (正規表現)
- `datetime` モジュール
- `typing` モジュール
- CloudWatchクライアント

**期待される結果**:
```
START RequestId: xxx
=== TEST WITH ALL IMPORTS ===
Event received: {...}
EMAIL_SNS_TOPIC_ARN: arn:aws:sns:...
boto3 SNS client created successfully
boto3 CloudWatch Logs client created successfully
boto3 CloudWatch client created successfully
Current time: 2025-01-08 12:00:00.000000
Regex test successful: 123
=== TEST COMPLETED ===
END RequestId: xxx
```

**確認ポイント**:
- すべてのモジュールが正常にインポートできるか
- 各モジュールの基本機能が動作するか

---

## トラブルシューティング

### 問題1: Step 1で失敗 (START → END のみ)

**原因**: 
- Lambda関数の基本設定に問題
- ランタイム設定の問題
- ハンドラー設定の問題

**対策**:
1. **ランタイム**: Python 3.11 に設定
2. **ハンドラー**: `lambda_function.lambda_handler` に設定
3. Lambda関数を再作成

### 問題2: Step 2で失敗

**原因**: 
- 環境変数が設定されていない
- 環境変数の値が間違っている

**対策**:
1. Lambda関数の環境変数を確認
2. `EMAIL_SNS_TOPIC_ARN` を正しいSNSトピックARNに設定

### 問題3: Step 3で失敗

**原因**: 
- IAM権限不足
- boto3の問題

**対策**:
1. Lambda実行ロールの権限を確認
2. 必要なIAMポリシーをアタッチ

### 問題4: Step 4で失敗

**原因**: 
- 特定のモジュールの問題
- Python環境の問題

**対策**:
1. エラーメッセージを確認
2. 問題のあるモジュールを特定
3. 代替手段を検討

---

## 成功後の次のステップ

すべてのステップが成功したら:

1. **デバッグ版の本番コード**をテスト
2. **実際のCloudWatchアラーム**でテスト
3. **メール通知**の動作確認

---

## 注意事項

- 各ステップは**順番に**実行してください
- 失敗したステップで**原因を特定**してから次に進んでください
- テスト後は**本番用のコード**に戻すことを忘れずに