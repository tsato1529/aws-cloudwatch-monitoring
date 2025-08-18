import json
import boto3
import os
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

def lambda_handler(event, context):
    print("=== LAMBDA FUNCTION STARTED ===")
    print(f"Event type: {type(event)}")
    print(f"Event keys: {list(event.keys()) if isinstance(event, dict) else 'Not a dict'}")
    print("=== EVENT RECEIVED ===")
    print(json.dumps(event, indent=2, default=str))
    
    try:
        print("=== CHECKING ENVIRONMENT VARIABLES ===")
        email_sns_topic_arn = os.environ.get('EMAIL_SNS_TOPIC_ARN')
        print(f"EMAIL_SNS_TOPIC_ARN: {email_sns_topic_arn}")
        
        if not email_sns_topic_arn:
            print("ERROR: EMAIL_SNS_TOPIC_ARN environment variable not set")
            raise ValueError("EMAIL_SNS_TOPIC_ARN environment variable not set")
        
        print("=== PROCESSING EVENT ===")
        # CloudWatchアラームからのイベントを処理
        if 'Records' in event:
            print("Processing SNS Records...")
            # SNS経由でのイベント
            for i, record in enumerate(event['Records']):
                print(f"Record {i}: EventSource = {record.get('EventSource', 'Unknown')}")
                if record.get('EventSource') == 'aws:sns':
                    print(f"SNS Record found. Message content:")
                    message = json.loads(record['Sns']['Message'])
                    print(json.dumps(message, indent=2, default=str))
                    print("Calling process_alarm_event...")
                    process_alarm_event(message)
                    print("process_alarm_event completed")
                else:
                    print(f"Unknown event source: {record.get('EventSource')}")
        else:
            print("Processing direct CloudWatch alarm event...")
            # 直接のCloudWatchアラームイベント
            process_alarm_event(event)
            
        print("=== FUNCTION COMPLETED SUCCESSFULLY ===")
        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Error notification processed successfully"
            })
        }
        
    except Exception as e:
        print(f"=== ERROR OCCURRED ===")
        print(f"Error type: {type(e)}")
        print(f"Error message: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return {
            "statusCode": 500,
            "body": json.dumps({
                "message": f"Error: {str(e)}"
            })
        }

def process_alarm_event(alarm_data: Dict[str, Any]):
    """CloudWatchアラームイベントを処理（動的設定取得版）"""
    
    # 環境変数から必要最小限の設定のみ取得
    email_sns_topic_arn = os.environ.get('EMAIL_SNS_TOPIC_ARN')
    
    if not email_sns_topic_arn:
        raise ValueError("EMAIL_SNS_TOPIC_ARN environment variable not set")
    
    # SNS経由のCloudWatchアラームイベントの構造に対応
    old_state = 'UNKNOWN'
    alarm_arn = 'unknown'
    if 'AlarmName' in alarm_data:
        # SNS経由のCloudWatchアラーム形式（標準形式）
        alarm_name = alarm_data.get('AlarmName', 'Unknown')
        alarm_description = alarm_data.get('AlarmDescription', '')
        new_state = alarm_data.get('NewStateValue', 'UNKNOWN')
        reason = alarm_data.get('NewStateReason', '')
        timestamp = alarm_data.get('StateChangeTime', datetime.now().isoformat())
        old_state = alarm_data.get('OldStateValue', old_state)
        alarm_arn = alarm_data.get('AlarmArn', alarm_arn)
    elif 'alarmData' in alarm_data:
        # 直接呼び出し形式（後方互換性のため保持）
        alarm_info = alarm_data['alarmData']
        alarm_name = alarm_info.get('alarmName', 'Unknown')
        alarm_description = alarm_data.get('alarmDescription', '')
        state_info = alarm_info.get('state', {})
        new_state = state_info.get('value', 'UNKNOWN')
        reason = state_info.get('reason', '')
        timestamp = state_info.get('timestamp', datetime.now().isoformat())
    else:
        raise ValueError("Unknown alarm event format")
    
    print(f"Processing alarm: {alarm_name}, State: {new_state}")
    
    # アラーム状態がALARMの場合のみ処理
    if new_state == 'ALARM':
        try:
            # アラーム情報から動的にロググループ情報を取得
            log_group_info = get_log_group_info_from_alarm(alarm_name)
            
            log_group_name = log_group_info['log_group_name']
            filter_pattern = log_group_info['filter_pattern']
            display_name = log_group_info['display_name']
            description = log_group_info['description']
            
            print(f"Dynamic config - Log Group: {log_group_name}")
            print(f"Dynamic config - Filter Pattern: {filter_pattern}")
            print(f"Dynamic config - Display Name: {display_name}")
            
        except Exception as e:
            print(f"Error getting dynamic log group configuration: {e}")
            # フォールバック: アラーム名から推定して処理を継続（最小ルール）
            base = alarm_name
            if base.endswith('-Alarm'):
                base = base[:-len('-Alarm')]
            for suf in ('-Error', '-Warning', '-Critical', '-Info', '-Debug', '-Alert'):
                if base.lower().endswith(suf.lower()):
                    base = base[:-len(suf)]
                    break
            log_group_name = base
            filter_pattern = infer_filter_pattern_from_log_group_name(log_group_name)
            display_name = generate_display_name(log_group_name)
            description = generate_description(log_group_name)
            print('[Fallback] Using inferred config from alarm name')
            print(f"[Fallback] Log Group: {log_group_name}")
            print(f"[Fallback] Filter Pattern: {filter_pattern}")
            print(f"[Fallback] Display Name: {display_name}")
        
        print(f"Identified log group: {log_group_name}, filter: {filter_pattern}")
        
        # NewStateReasonからevaluatedDatapointsのタイムスタンプを抽出
        datapoint_timestamp = extract_datapoint_timestamp_from_reason(reason)
        print(f"Extracted datapoint timestamp: {datapoint_timestamp}")
        
        # 最近のエラーログを取得（改善された方法）
        if datapoint_timestamp:
            error_logs = get_logs_from_datapoint_period(log_group_name, filter_pattern, datapoint_timestamp)
            print(f"Retrieved {len(error_logs)} error logs using datapoint period method")
        else:
            # フォールバック: 従来の方法
            error_logs = get_recent_error_logs(log_group_name, filter_pattern)
            print(f"Retrieved {len(error_logs)} error logs using fallback method")
        
        # デバッグ: 取得したログの内容を出力
        for i, log in enumerate(error_logs[:3]):
            print(f"Log {i+1}: {log.get('message', '')[:100]}...")
        
        # メール内容を生成（件名と本文）
        search_method = "datapoint_period" if datapoint_timestamp else "fallback"
        subject, body = generate_email_content(
            alarm_name, alarm_description, timestamp, reason, error_logs,
            log_group_name, search_method,
            old_state=old_state, new_state=new_state, alarm_arn=alarm_arn
        )
        
        # デバッグ: メール内容を出力
        print(f"Email subject: {subject}")
        print(f"Email body preview: {body[:500]}...")
        
        # SNS経由でメール送信
        send_notification(email_sns_topic_arn, subject, body)

def get_log_group_info_from_alarm(alarm_name: str) -> Dict[str, str]:
    """
    CloudWatch APIを使用してアラームに関連するロググループとフィルターパターンを動的に取得
    """
    cloudwatch = boto3.client('cloudwatch')
    logs_client = boto3.client('logs')
    
    try:
        # 1. アラームの詳細情報を取得
        response = cloudwatch.describe_alarms(AlarmNames=[alarm_name])
        
        if not response['MetricAlarms']:
            raise ValueError(f"Alarm not found: {alarm_name}")
        
        alarm = response['MetricAlarms'][0]
        metric_name = alarm['MetricName']
        namespace = alarm['Namespace']
        
        print(f"Alarm metric: {namespace}/{metric_name}")
        
        # 2. アラーム名から直接ロググループ名を推定（新しい命名ルール）
        log_group_name = infer_log_group_name_from_alarm_name(alarm_name)
        
        # フォールバック: メトリクス情報からも推定を試行
        if not log_group_name:
            log_group_name = infer_log_group_name_from_metric(metric_name, namespace)
        
        # 3. ロググループの存在確認
        verify_log_group_exists(logs_client, log_group_name)
        
        # 4. メトリクスフィルターからフィルターパターンを取得
        filter_pattern = get_filter_pattern_from_log_group(logs_client, log_group_name, metric_name)
        
        # 5. 表示名と説明を生成
        display_name = generate_display_name(log_group_name)
        description = generate_description(log_group_name)
        
        return {
            "log_group_name": log_group_name,
            "display_name": display_name,
            "filter_pattern": filter_pattern,
            "description": description
        }
        
    except Exception as e:
        print(f"Error getting log group info from alarm: {e}")
        raise

def infer_log_group_name_from_alarm_name(alarm_name: str) -> str:
    """
    アラーム名からロググループ名を推定（汎用・最小ルール）
    規約: アラーム名 = <LogGroupName>-<Severity>-Alarm
    → ロググループ名は、末尾の "-Alarm" と "-<Severity>" を順に取り除いたもの
    （Severityは Error/Warning/Critical/Info/Debug/Alert を想定。大文字小文字は区別しない）
    """
    base = alarm_name
    # 末尾の -Alarm を除去
    if base.endswith("-Alarm"):
        base = base[: -len("-Alarm")]
    # 末尾の Severity を除去（大小文字を問わず）
    severities = ("-Error", "-Warning", "-Critical", "-Info", "-Debug", "-Alert")
    for suf in severities:
        if base.lower().endswith(suf.lower()):
            base = base[: -len(suf)]
            break
    print(f"Inferred log group name from alarm '{alarm_name}': {base}")
    return base

def infer_log_group_name_from_metric(metric_name: str, namespace: str) -> str:
    """
    メトリクス名と名前空間からロググループ名を推定（後方互換性のため保持）
    """
    if namespace == "LS-AWSLAB-ErrorMonitoring":
        # 新しい命名規則: "EC2-MTA01-Messages-Error" → "LS-AWSLAB-EC2-MTA01-Messages"
        log_group_suffix = metric_name.replace("-Error", "")
        log_group_name = f"LS-AWSLAB-{log_group_suffix}"
            
    elif namespace == "LS-AWSLAB-EC2-MTA01":
        # 既存の命名規則（後方互換性）
        if "messages" in metric_name.lower():
            log_group_name = "LS-AWSLAB-EC2-MTA01-Log-messages"
        elif "app" in metric_name.lower():
            log_group_name = "LS-AWSLAB-EC2-MTA01-Log-app"
        else:
            log_group_name = "LS-AWSLAB-EC2-MTA01-Log-messages"  # デフォルト
    else:
        raise ValueError(f"Unknown namespace: {namespace}")
    
    return log_group_name

def verify_log_group_exists(logs_client, log_group_name: str):
    """
    ロググループの存在確認
    """
    try:
        response = logs_client.describe_log_groups(
            logGroupNamePrefix=log_group_name,
            limit=1
        )
        
        if not response['logGroups'] or response['logGroups'][0]['logGroupName'] != log_group_name:
            raise ValueError(f"Log group not found: {log_group_name}")
            
        print(f"Log group verified: {log_group_name}")
        
    except Exception as e:
        print(f"Error verifying log group: {e}")
        raise

def get_filter_pattern_from_log_group(logs_client, log_group_name: str, metric_name: str) -> str:
    """
    ロググループのメトリクスフィルターから実際のフィルターパターンを取得
    """
    try:
        # ロググループのメトリクスフィルターを取得
        response = logs_client.describe_metric_filters(
            logGroupName=log_group_name
        )
        
        metric_filters = response.get('metricFilters', [])
        
        if not metric_filters:
            print(f"No metric filters found for log group: {log_group_name}")
            # フォールバック: ロググループ名から推定
            return infer_filter_pattern_from_log_group_name(log_group_name)
        
        # 複数のメトリクスフィルターがある場合、メトリクス名で特定
        target_filter = None
        for filter_info in metric_filters:
            for transformation in filter_info.get('metricTransformations', []):
                if transformation.get('metricName') == metric_name:
                    target_filter = filter_info
                    break
            if target_filter:
                break
        
        if target_filter:
            filter_pattern = target_filter.get('filterPattern', '')
            print(f"Found filter pattern from metric filter: {filter_pattern}")
            return filter_pattern
        else:
            # メトリクス名が一致しない場合、最初のフィルターを使用
            filter_pattern = metric_filters[0].get('filterPattern', '')
            print(f"Using first available filter pattern: {filter_pattern}")
            return filter_pattern
            
    except Exception as e:
        print(f"Error getting filter pattern from metric filters: {e}")
        # フォールバック: ロググループ名から推定
        return infer_filter_pattern_from_log_group_name(log_group_name)

def infer_filter_pattern_from_log_group_name(log_group_name: str) -> str:
    """
    ロググループ名からフィルターパターンを推定（フォールバック用）
    新しい命名ルール対応
    """
    log_group_lower = log_group_name.lower()
    
    # 新しい命名ルール: ロググループ名の末尾で判定
    if log_group_lower.endswith("-messages"):
        return "[error]"
    elif log_group_lower.endswith("-app"):
        return "ERROR"
    # 後方互換性: 古い命名規則
    elif "log-messages" in log_group_lower:
        return "[error]"
    elif "log-app" in log_group_lower:
        return "ERROR"
    else:
        return "ERROR"  # デフォルト

# def generate_display_name(log_group_name: str) -> str:
#     """
#     ロググループ名から表示名を生成
#     新しい命名ルール: ロググループ名から"LS-AWSLAB-"プレフィックスを削除
#     """
#     # "LS-AWSLAB-EC2-MTA01-Messages" → "EC2-MTA01-Messages"
#     if log_group_name.startswith("LS-AWSLAB-"):
#         display_name = log_group_name.replace("LS-AWSLAB-", "")
#     else:
#         display_name = log_group_name
#     
#     # 後方互換性: 古い命名規則にも対応
#     if display_name.endswith("-Log-messages"):
#         display_name = display_name.replace("-Log-messages", "-Messages")
#     elif display_name.endswith("-Log-app"):
#         display_name = display_name.replace("-Log-app", "-App")
#     
#     return display_name
    """
    ロググループ名から表示名を生成
    新しい命名ルール: ロググループ名から"LS-AWSLAB-"プレフィックスを削除
    """
    # "LS-AWSLAB-EC2-MTA01-Messages" → "EC2-MTA01-Messages"
    if log_group_name.startswith("LS-AWSLAB-"):
        display_name = log_group_name.replace("LS-AWSLAB-", "")
    else:
        display_name = log_group_name
    
    # 後方互換性: 古い命名規則にも対応
    if display_name.endswith("-Log-messages"):
        display_name = display_name.replace("-Log-messages", "-Messages")
    elif display_name.endswith("-Log-app"):
        display_name = display_name.replace("-Log-app", "-App")
    
    return display_name

def generate_display_name(log_group_name: str) -> str:
    """ロググループ名から表示名を生成（後方互換に配慮）"""
    base = log_group_name
    if base.startswith("LS-AWSLAB-"):
        base = base.replace("LS-AWSLAB-", "", 1)
    if base.endswith("-Log-messages"):
        base = base.replace("-Log-messages", "-Messages")
    elif base.endswith("-Log-app"):
        base = base.replace("-Log-app", "-App")
    return base


def generate_description(log_group_name: str) -> str:
    """
    ロググループの説明を生成
    新しい命名ルール対応
    """
    log_group_lower = log_group_name.lower()
    
    # 新しい命名ルール: ロググループ名の末尾で判定
    if log_group_lower.endswith("-messages"):
        log_type = "システムメッセージ"
    elif log_group_lower.endswith("-app"):
        log_type = "アプリケーション"
    # 後方互換性: 古い命名規則
    elif "log-messages" in log_group_lower:
        log_type = "システムメッセージ"
    elif "log-app" in log_group_lower:
        log_type = "アプリケーション"
    else:
        log_type = "アプリケーション"
    
    # インスタンス/サービス名を抽出（ロググループ名から推定）
    base = log_group_name.replace("LS-AWSLAB-", "")
    # 例: EC2-MTA01-Log-app / EC2-MTA01-Log-messages → EC2-MTA01
    parts = base.split("-")
    if len(parts) >= 2:
        instance_name = f"{parts[0]}-{parts[1]}"
    else:
        instance_name = base

    return f"{instance_name}の{log_type}ログ"

def extract_datapoint_timestamp_from_reason(state_reason: str) -> Optional[str]:
    """
    NewStateReasonからevaluatedDatapointsのタイムスタンプを抽出
    
    Args:
        state_reason: CloudWatchアラームのNewStateReason
        例: "Threshold Crossed: 1 datapoint [2.0 (04/08/25 05:16:00)] was greater than..."
    
    Returns:
        str: ISO形式のタイムスタンプ ("2025-08-04T05:16:00.000Z") または None
    """
    if not state_reason:
        return None
    
    try:
        # パターン1: (YY/MM/DD HH:MM:SS) 形式
        pattern1 = r'\((\d{2}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})\)'
        match1 = re.search(pattern1, state_reason)
        
        if match1:
            timestamp_str = match1.group(1)  # "05/08/25 04:05:00"
            print(f"Matched timestamp pattern: {timestamp_str}")
            
            # YY/MM/DD形式を正しく解釈（25 = 2025年）
            # 日付形式: DD/MM/YY なので、年は最後の2桁
            parts = timestamp_str.split(' ')
            date_part = parts[0]  # "05/08/25"
            time_part = parts[1]  # "04:05:00"
            
            date_components = date_part.split('/')  # ["05", "08", "25"]
            year_part = date_components[2]  # "25"
            
            if int(year_part) <= 50:  # 00-50は20xx年、51-99は19xx年
                full_year = f"20{year_part}"
            else:
                full_year = f"19{year_part}"
            
            # 正しい年を使って日付を構築 (YYYY/MM/DD HH:MM:SS)
            corrected_timestamp = f"{full_year}/{date_components[1]}/{date_components[0]} {time_part}"
            print(f"Corrected timestamp: {corrected_timestamp}")
            dt = datetime.strptime(corrected_timestamp, "%Y/%m/%d %H:%M:%S")
            iso_timestamp = dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
            
            return iso_timestamp
        
        # パターン2: 他の形式があれば追加可能
        # pattern2 = r'...'
        
        print(f"No timestamp pattern matched in: {state_reason}")
        return None
        
    except Exception as e:
        print(f"Error extracting timestamp from state reason: {e}")
        return None

def get_logs_from_datapoint_period(log_group_name: str, filter_pattern: str, 
                                 datapoint_timestamp: str) -> List[Dict[str, Any]]:
    """
    evaluatedDatapointsのタイムスタンプを基準にしたログ取得
    
    Args:
        log_group_name: ロググループ名
        filter_pattern: フィルターパターン
        datapoint_timestamp: evaluatedDatapointsのタイムスタンプ (ISO形式)
    
    Returns:
        list: エラーログのリスト
    """
    logs_client = boto3.client('logs')
    
    try:
        # タイムスタンプをdatetimeオブジェクトに変換
        start_time = datetime.fromisoformat(datapoint_timestamp.replace('Z', '+00:00'))
        
        # Periodを取得（現在は固定値、将来的にはアラーム設定から取得可能）
        # TODO: アラーム設定から動的に取得する方法を検討
        period_seconds = 300  # 5分間（現在の設定）
        
        end_time = start_time + timedelta(seconds=period_seconds)
        
        print(f"Searching logs from {start_time} to {end_time} (period: {period_seconds}s)")
        
        # フィルターパターンを正規化
        if filter_pattern == "[error]":
            search_pattern = "error"
        else:
            search_pattern = filter_pattern
        
        response = logs_client.filter_log_events(
            logGroupName=log_group_name,
            startTime=int(start_time.timestamp() * 1000),
            endTime=int(end_time.timestamp() * 1000),
            filterPattern=search_pattern,
            limit=20  # 少し多めに取得
        )
        
        events = response.get('events', [])
        
        # タイムスタンプ順にソート（新しい順）
        events.sort(key=lambda x: x['timestamp'], reverse=True)
        
        print(f"Found {len(events)} logs in datapoint period")
        return events[:10]  # 最大10件を返す
        
    except Exception as e:
        print(f"Error fetching logs from datapoint period: {e}")
        return []

def get_recent_error_logs(log_group_name: str, filter_pattern: str, hours_back: int = 1) -> List[Dict[str, Any]]:
    """最近のエラーログを取得"""
    
    logs_client = boto3.client('logs')
    
    # 検索期間を設定（過去1時間）
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=hours_back)
    
    try:
        # フィルターパターンを正規化（CloudWatch Logsの形式に合わせる）
        if filter_pattern == "[error]":
            # 既存のパターンはそのまま使用
            search_pattern = "error"
        else:
            # 新しいパターンはそのまま使用
            search_pattern = filter_pattern
        
        response = logs_client.filter_log_events(
            logGroupName=log_group_name,
            startTime=int(start_time.timestamp() * 1000),
            endTime=int(end_time.timestamp() * 1000),
            filterPattern=search_pattern,
            limit=10  # 最大10件のエラーログを取得
        )
        
        return response.get('events', [])
        
    except Exception as e:
        print(f"Error fetching logs from {log_group_name}: {str(e)}")
        return []

def generate_email_content(alarm_name: str, alarm_description: str, 
                         timestamp: str, reason: str, 
                         error_logs: List[Dict[str, Any]], 
                         log_group_name: str,
                         search_method: str = "unknown",
                         old_state: Optional[str] = None,
                         new_state: Optional[str] = None,
                         alarm_arn: Optional[str] = None) -> tuple:
    """メールの件名と本文を生成（デフォルトSNSメールに準拠＋日本語の追加情報）"""

    # リージョン表記
    region_code = os.environ.get('AWS_REGION', 'ap-northeast-1')
    region_long = {
        'ap-northeast-1': 'Asia Pacific (Tokyo)'
    }.get(region_code, region_code)

    # アカウントID（デフォルトメールの表記に近づけるため）
    try:
        sts = boto3.client('sts')
        account_id = sts.get_caller_identity().get('Account', 'unknown')
    except Exception:
        account_id = 'unknown'

    # 件名（SNSデフォルトに準拠）
    subject = f'ALARM: "{alarm_name}" in {region_long}'

    # デフォルトSNSメール風の本文（英語ベース）
    header = (
        f"You are receiving this email because your Amazon CloudWatch Alarm \"{alarm_name}\" "
        f"in the {region_long} region has entered the ALARM state, because \"{reason}\" "
        f"at \"{timestamp}\".\n\n"
    )

    details = (
        "Alarm Details:\n"
        f"- Name: {alarm_name}\n"
        f"- Description: {alarm_description}\n"
        f"- Timestamp: {timestamp}\n"
        f"- State Change: {old_state or 'UNKNOWN'} -> {new_state or 'UNKNOWN'}\n"
        f"- Reason for State Change: {reason}\n"
        f"- AWS Account: {account_id}\n"
        f"- Alarm Arn: {alarm_arn or 'unknown'}\n"
        f"- Region: {region_code}\n"
    )

    # 追加セクション（日本語）
    body_extra = "\n【検出されたエラーログ（追加情報）】\n"
    if error_logs:
        if search_method == "datapoint_period":
            body_extra += f"アラーム発生のメトリクス期間（5分間）で {len(error_logs)} 件のエラーが検出されました:\n\n"
        else:
            body_extra += f"過去1時間で {len(error_logs)} 件のエラーが検出されました:\n\n"
        for i, log_event in enumerate(error_logs[:5], 1):
            log_time = datetime.fromtimestamp(log_event['timestamp'] / 1000)
            message = log_event['message']
            if len(message) > 300:
                message = message[:300] + "..."
            body_extra += f"{i}. {log_time.strftime('%Y-%m-%d %H:%M:%S')}\n   {message}\n\n"
        if len(error_logs) > 5:
            body_extra += f"... 他 {len(error_logs) - 5} 件のエラーログがあります\n\n"
    else:
        body_extra += "詳細なエラーログの取得に失敗しました。\n\n"

    # CloudWatch Alarm コンソールリンク（Alarm Details の前に表示）
    import urllib.parse
    encoded_alarm_name = urllib.parse.quote(alarm_name, safe='')
    alarm_console_link = (
        "View this alarm in the AWS Management Console:\n"
        f"https://console.aws.amazon.com/cloudwatch/home?region={region_code}#alarmsV2:alarm/{encoded_alarm_name}\n\n"
    )

    # Threshold + Monitored Metric + State Change Actions blocks (Alarm Details の後に表示)
    monitored_metric_block = "Monitored Metric:\n- (not available)\n\n"
    state_change_actions_block = (
        "State Change Actions:\n"
        "- OK: None\n"
        "- ALARM: None\n"
        "- INSUFFICIENT_DATA: None\n\n"
    )
    try:
        cw = boto3.client('cloudwatch')
        resp = cw.describe_alarms(AlarmNames=[alarm_name])
        if resp.get('MetricAlarms'):
            al = resp['MetricAlarms'][0]
            comp = al.get('ComparisonOperator')
            thr = al.get('Threshold')
            evalp = al.get('EvaluationPeriods')
            d2a = al.get('DatapointsToAlarm')
            period = al.get('Period')
            n_dp = d2a if d2a is not None else evalp
            if comp and thr is not None and n_dp is not None and period is not None:
                sentence = f"- The alarm is in the ALARM state when the metric is {comp} {thr} for {n_dp} datapoints within {period} seconds.\n\n"
            else:
                sentence = "- The alarm is in the ALARM state when the metric crosses the configured threshold.\n\n"
            threshold_block = "Threshold:\n" + sentence

            # Monitored Metric
            ns = al.get('Namespace')
            mn = al.get('MetricName')
            stat = al.get('Statistic') or al.get('ExtendedStatistic')
            unit = al.get('Unit')
            tmd = al.get('TreatMissingData')
            dims = al.get('Dimensions', [])
            dim_str = ", ".join([f"{d.get('Name')}={d.get('Value')}" for d in dims]) if dims else "None"
            mm_lines = [
                "Monitored Metric:",
                f"- MetricNamespace: {ns if ns is not None else 'None'}",
                f"- MetricName: {mn if mn is not None else 'None'}",
                f"- Dimensions: {dim_str}",
                f"- Period: {period} seconds" if period is not None else "- Period: None",
                f"- Statistic: {stat}" if stat else "- Statistic: None",
                f"- Unit: {unit if unit is not None else 'None'}",
                f"- TreatMissingData: {tmd if tmd is not None else 'None'}",
            ]
            monitored_metric_block = "\n".join(mm_lines) + "\n\n"

            # State Change Actions
            def _fmt_actions(actions):
                if actions:
                    return ", ".join(actions)
                return "None"
            sca_lines = [
                "State Change Actions:",
                f"- OK: {_fmt_actions(al.get('OKActions'))}",
                f"- ALARM: {_fmt_actions(al.get('AlarmActions'))}",
                f"- INSUFFICIENT_DATA: {_fmt_actions(al.get('InsufficientDataActions'))}",
            ]
            state_change_actions_block = "\n".join(sca_lines) + "\n\n"
        else:
            threshold_block = "Threshold:\n- The alarm is in the ALARM state when the metric crosses the configured threshold.\n\n"
    except Exception:
        threshold_block = "Threshold:\n- The alarm is in the ALARM state when the metric crosses the configured threshold.\n\n"

    # 注意喚起（SNSのunsubscribeリンク直前に表示されるよう本文末尾に追記）
    caution_block = (
        "【重要】購読解除に関する注意\n"
        "本メールの末尾に表示される Amazon SNS の unsubscribe リンクをクリックすると、"
        "本アラートメールが届かなくなります。運用に支障が出るため、承認を得た場合のみ実施してください。\n\n"
    )

    body = header + body_extra + alarm_console_link + details + "\n" + threshold_block + monitored_metric_block + state_change_actions_block + caution_block
    return subject, body

def send_notification(sns_topic_arn: str, subject: str, body: str):
    """SNS経由でメール通知を送信"""
    
    sns_client = boto3.client('sns')
    
    try:
        # 直接SESを使用してunsubscribeリンクを回避
        # まずはSNSで送信（既存の仕組みを維持）
        response = sns_client.publish(
            TopicArn=sns_topic_arn,
            Subject=subject,
            Message=body
        )
        
        print(f"Notification sent successfully. MessageId: {response['MessageId']}")
        
    except Exception as e:
        print(f"Error sending notification: {str(e)}")
        raise

