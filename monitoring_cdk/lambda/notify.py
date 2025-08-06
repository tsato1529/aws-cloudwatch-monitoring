import json
import boto3
import os
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

def handler(event, context):
    print("=== EVENT RECEIVED ===")
    print(json.dumps(event))
    
    try:
        # CloudWatchアラームからのイベントを処理
        if 'Records' in event:
            # SNS経由でのイベント
            for record in event['Records']:
                if record['EventSource'] == 'aws:sns':
                    message = json.loads(record['Sns']['Message'])
                    process_alarm_event(message)
        else:
            # 直接のCloudWatchアラームイベント
            process_alarm_event(event)
            
        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Error notification processed successfully"
            })
        }
        
    except Exception as e:
        print(f"Error processing event: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps({
                "message": f"Error: {str(e)}"
            })
        }

def process_alarm_event(alarm_data: Dict[str, Any]):
    """CloudWatchアラームイベントを処理"""
    
    # 環境変数から設定を取得
    email_sns_topic_arn = os.environ.get('EMAIL_SNS_TOPIC_ARN')
    log_groups_config_str = os.environ.get('LOG_GROUPS_CONFIG')
    
    if not email_sns_topic_arn or not log_groups_config_str:
        raise ValueError("Required environment variables not set")
    
    # ロググループ設定をパース
    try:
        log_groups_config = json.loads(log_groups_config_str)
    except json.JSONDecodeError:
        raise ValueError("Invalid LOG_GROUPS_CONFIG format")
    
    # SNS経由のCloudWatchアラームイベントの構造に対応
    if 'AlarmName' in alarm_data:
        # SNS経由のCloudWatchアラーム形式（標準形式）
        alarm_name = alarm_data.get('AlarmName', 'Unknown')
        alarm_description = alarm_data.get('AlarmDescription', '')
        new_state = alarm_data.get('NewStateValue', 'UNKNOWN')
        reason = alarm_data.get('NewStateReason', '')
        timestamp = alarm_data.get('StateChangeTime', datetime.now().isoformat())
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
        # アラーム名からロググループを特定
        log_group_info = identify_log_group_from_alarm(alarm_name, log_groups_config)
        if not log_group_info:
            print(f"Warning: Could not identify log group for alarm: {alarm_name}")
            return
        
        log_group_name = log_group_info['name']
        filter_pattern = log_group_info['config']['filter_pattern']
        display_name = log_group_info['config']['display_name']
        
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
            log_group_name, display_name, search_method
        )
        
        # デバッグ: メール内容を出力
        print(f"Email subject: {subject}")
        print(f"Email body preview: {body[:500]}...")
        
        # SNS経由でメール送信
        send_notification(email_sns_topic_arn, subject, body)

def identify_log_group_from_alarm(alarm_name: str, log_groups_config: Dict[str, Any]) -> Dict[str, Any]:
    """アラーム名からロググループを特定"""
    
    # アラーム名のパターン: LS-AWSLAB-{display_name}-Error-Alarm
    for log_group_name, config in log_groups_config.items():
        display_name = config['display_name']
        expected_alarm_name = f"LS-AWSLAB-{display_name}-Error-Alarm"
        
        if alarm_name == expected_alarm_name:
            return {
                'name': log_group_name,
                'config': config
            }
    
    # 既存のアラーム名との互換性（MTA01の場合）
    if alarm_name == "LS-AWSLAB-EC2-MTA01-Error-Alarm":
        for log_group_name, config in log_groups_config.items():
            if log_group_name == "LS-AWSLAB-EC2-MTA01-Log-messages":
                return {
                    'name': log_group_name,
                    'config': config
                }
    
    return None

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
                         log_group_name: str, display_name: str,
                         search_method: str = "unknown") -> tuple:
    """メールの件名と本文を生成"""
    
    # 件名
    subject = f"🚨 AWS Alert: {display_name} - エラーが検出されました"
    
    # ログタイプに応じた説明を生成
    log_type_descriptions = {
        "EC2-MTA01-Messages": "EC2インスタンス(awslab-mta01)のシステムログ",
        "EC2-MTA01-App": "EC2インスタンス(awslab-mta01)のアプリケーションログ", 
        "APIGW-mtkhs-App01": "API Gateway(mtkhs-App01)",
        "Lambda-mtkhs-App01": "Lambda関数(mtkhs-App01)"
    }
    
    log_description = log_type_descriptions.get(display_name, f"{display_name}のログ")
    
    # 本文
    body = f"""
AWS CloudWatchアラームが発生しました。

【アラーム情報】
・アラーム名: {alarm_name}
・対象ログ: {log_description}
・ロググループ: {log_group_name}
・説明: {alarm_description}
・発生時刻: {timestamp}
・理由: {reason}

【検出されたエラーログ】
"""
    
    if error_logs:
        # 検索方法に応じた説明を生成
        if search_method == "datapoint_period":
            body += f"アラーム発生の原因となったメトリクス期間（5分間）で {len(error_logs)} 件のエラーが検出されました:\n\n"
        else:
            body += f"過去1時間で {len(error_logs)} 件のエラーが検出されました:\n\n"
        
        for i, log_event in enumerate(error_logs[:5], 1):  # 最大5件表示
            log_time = datetime.fromtimestamp(log_event['timestamp'] / 1000)
            message = log_event['message']
            
            # エラーメッセージを整形（長すぎる場合は切り詰め）
            if len(message) > 300:
                message = message[:300] + "..."
            
            body += f"{i}. {log_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            body += f"   {message}\n\n"
            
        if len(error_logs) > 5:
            body += f"... 他 {len(error_logs) - 5} 件のエラーログがあります\n\n"
    else:
        body += "詳細なエラーログの取得に失敗しました。\n\n"
    
    # 対応方法ブロックを削除（不要なため）
    action_guide = ""
    
    # URLエンコードされたロググループ名を生成
    import urllib.parse
    encoded_log_group = urllib.parse.quote(log_group_name, safe='')
    
    body += f"""
【ログ確認URL】
https://ap-northeast-1.console.aws.amazon.com/cloudwatch/home?region=ap-northeast-1#logsV2:log-groups/log-group/{encoded_log_group}

このメールは自動送信されています。
"""
    
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

