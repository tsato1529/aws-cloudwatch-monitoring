import json
from aws_cdk import (
    Stack,
    aws_lambda as lambda_,
    aws_sns as sns,
    aws_sns_subscriptions as subs,
    aws_cloudwatch as cloudwatch,
    aws_cloudwatch_actions as cw_actions,
    aws_iam as iam,
    Duration
)
from constructs import Construct

class MonitoringCdkStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # 監視対象ロググループの設定（EC2-MTA01の2つのみ）
        log_groups_config = [
            {
                "name": "LS-AWSLAB-EC2-MTA01-Log-messages",
                "display_name": "EC2-MTA01-Messages",
                "filter_pattern": "[error]",
                "description": "EC2インスタンス(MTA01)のシステムメッセージログ"
            },
            {
                "name": "LS-AWSLAB-EC2-MTA01-Log-app", 
                "display_name": "EC2-MTA01-App",
                "filter_pattern": "ERROR",
                "description": "EC2インスタンス(MTA01)のアプリケーションログ"
            }
        ]

        # アラーム処理用SNSトピック（Lambda関数のトリガー用）
        self.alarm_processing_topic = sns.Topic(
            self, "AlarmProcessingTopic",
            display_name="CloudWatch Alarm Processing",
            topic_name="LS-AWSLAB-CloudWatchAlarmProcessing"
        )

        # メール通知用SNSトピック（最終的な通知先）
        self.email_notification_topic = sns.Topic(
            self, "EmailNotificationTopic",
            display_name="Error Notifications via Email",
            topic_name="LS-AWSLAB-ErrorNotificationEmail"
        )

        # メール通知トピックへのメールサブスクリプション
        self.email_notification_topic.add_subscription(
            subs.EmailSubscription("takaaki.sato@librasolutions.co.jp")
        )
        
        # 汎用Lambda関数(Dockerイメージ使用)
        notify_function = lambda_.DockerImageFunction(
            self, "NotifyFunction",
            code=lambda_.DockerImageCode.from_image_asset("lambda"),
            timeout=Duration.minutes(5),
            environment={
                "EMAIL_SNS_TOPIC_ARN": self.email_notification_topic.topic_arn
            }
        )
        
        # Lambda関数にCloudWatch LogsとSNSの権限を付与（全ロググループ対象）
        log_group_arns = [
            f"arn:aws:logs:{self.region}:{self.account}:log-group:{config['name']}:*"
            for config in log_groups_config
        ]
        
        notify_function.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "logs:FilterLogEvents",
                    "logs:GetLogEvents",
                    "logs:DescribeLogStreams"
                ],
                resources=log_group_arns
            )
        )
        
        # 動的設定取得のための追加権限
        notify_function.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "cloudwatch:DescribeAlarms",
                    "logs:DescribeLogGroups",
                    "logs:DescribeMetricFilters"
                ],
                resources=["*"]
            )
        )
        
        # メール送信用SNSトピックへの発行権限
        self.email_notification_topic.grant_publish(notify_function)
        
        # アラーム処理用SNSトピックからLambda関数へのサブスクリプション
        self.alarm_processing_topic.add_subscription(
            subs.LambdaSubscription(notify_function)
        )
        
        # 各ロググループに対してメトリクスフィルターとアラームを作成
        self._create_monitoring_resources(log_groups_config, notify_function)

    def _create_monitoring_resources(self, log_groups_config, notify_function):
        """各ロググループに対してメトリクスフィルターとアラームを作成"""
        
        for config in log_groups_config:
            log_group_name = config["name"]
            display_name = config["display_name"]
            filter_pattern = config["filter_pattern"]
            description = config["description"]
            
            # メトリクス名前空間とメトリクス名を生成
            namespace = f"LS-AWSLAB-ErrorMonitoring"
            metric_name = f"{display_name}-Error"
            
            # 既存のメトリクスフィルターをチェック（MTA01-Messagesのみ既存）
            if log_group_name == "LS-AWSLAB-EC2-MTA01-Log-messages":
                # 既存のメトリクスを使用
                error_metric = cloudwatch.Metric(
                    namespace="LS-AWSLAB-EC2-MTA01",
                    metric_name="LS-AWSLAB-EC2-MTA01-Log-messages-Error",
                    statistic="Sum",
                    period=Duration.minutes(5)
                )
                print(f"Using existing metric: LS-AWSLAB-EC2-MTA01/LS-AWSLAB-EC2-MTA01-Log-messages-Error")
            else:
                # 新しいメトリクスフィルターを作成
                error_metric = cloudwatch.Metric(
                    namespace=namespace,
                    metric_name=metric_name,
                    statistic="Sum",
                    period=Duration.minutes(5)
                )
            
            # CloudWatchアラーム作成
            alarm_id = display_name.replace("-", "")
            error_alarm = cloudwatch.Alarm(
                self, f"ErrorAlarm{alarm_id}",
                alarm_name=f"LS-AWSLAB-{display_name}-Error-Alarm",
                alarm_description=f"{description}でエラーが検出されました",
                metric=error_metric,
                threshold=1,
                evaluation_periods=1,
                comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
                treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
            )
            
            # アラームがトリガーされたときにSNSトピックに通知
            error_alarm.add_alarm_action(
                cw_actions.SnsAction(self.alarm_processing_topic)
            )
