import json
import boto3
import os
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple


def normalize_filter_pattern(pattern: Optional[str]) -> str:\n    """Normalize CloudWatch Logs filter patterns for filter_log_events."""
    if pattern is None:
        return ""
    p = str(pattern).strip()
    if (p.startswith('"') and p.endswith('"')) or (p.startswith("'") and p.endswith("'")):
        p = p[1:-1].strip()
    if p.lower() == "[error]":
        return "error"
    return p


def get_log_group_info_from_trigger(alarm_message: Dict[str, Any]) -> Dict[str, str]:
    """
    Resolve logGroupName and filterPattern via Trigger in the CloudWatch Alarm SNS message.
    Supports simple metric (Trigger.MetricName/Namespace) and metric math (Trigger.Metrics[].MetricStat.Metric...).
    """
    trigger = alarm_message.get("Trigger")
    if not trigger:
        raise ValueError("Trigger not found in alarm message")

    candidates: List[Tuple[str, str]] = []

    # Simple metric
    if isinstance(trigger, dict) and "MetricName" in trigger and "Namespace" in trigger:
        candidates.append((trigger.get("Namespace"), trigger.get("MetricName")))

    # Metric math
    metrics = trigger.get("Metrics") if isinstance(trigger, dict) else None
    if isinstance(metrics, list):
        for m in metrics:
            metric_stat = m.get("MetricStat") if isinstance(m, dict) else None
            if not metric_stat:
                continue
            metric = metric_stat.get("Metric")
            if not isinstance(metric, dict):
                continue
            ns = metric.get("Namespace")
            mn = metric.get("MetricName")
            if ns and mn:
                candidates.append((ns, mn))

    if not candidates:
        raise ValueError("No metric candidates found in Trigger")

    logs_client = boto3.client("logs")
    found_filters: List[Dict[str, Any]] = []
    for ns, mn in candidates:
        try:
            resp = logs_client.describe_metric_filters(metricName=mn, metricNamespace=ns)
            found_filters.extend(resp.get("metricFilters", []))
        except Exception as e:
            print(f"describe_metric_filters error for {ns}/{mn}: {e}")

    if not found_filters:
        raise ValueError("No metric filters matched by Trigger's metrics")

    chosen = found_filters[0]
    return {
        "log_group_name": chosen.get("logGroupName"),
        "filter_pattern": chosen.get("filterPattern", "")
    }


def extract_datapoint_timestamp_from_reason(state_reason: str) -> Optional[str]:
    """Extract evaluated datapoint timestamp (ISO) from NewStateReason."""
    if not state_reason:
        return None
    try:
        m = re.search(r"\((\d{2}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})\)", state_reason)
        if not m:
            print(f"No timestamp pattern matched in: {state_reason}")
            return None
        ts = m.group(1)  # e.g. "28/08/25 04:22:00"
        dd, mm, yy = ts.split(" ")[0].split("/")  # DD/MM/YY
        hhmmss = ts.split(" ")[1]
        full_year = f"20{yy}" if int(yy) <= 50 else f"19{yy}"
        corrected = f"{full_year}/{mm}/{dd} {hhmmss}"
        dt = datetime.strptime(corrected, "%Y/%m/%d %H:%M:%S")
        return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    except Exception as e:
        print(f"Error extracting timestamp from state reason: {e}")
        return None


def get_logs_from_datapoint_period(log_group_name: str, filter_pattern: str, datapoint_timestamp: str) -> List[Dict[str, Any]]:
    """Fetch logs within the alarm datapoint period (default 5 minutes)."""
    logs_client = boto3.client("logs")
    try:
        start_time = datetime.fromisoformat(datapoint_timestamp.replace("Z", "+00:00"))
        period_seconds = 300
        end_time = start_time + timedelta(seconds=period_seconds)
        print(f"Searching logs from {start_time} to {end_time} (period: {period_seconds}s)")
        search_pattern = normalize_filter_pattern(filter_pattern)
        resp = logs_client.filter_log_events(
            logGroupName=log_group_name,
            startTime=int(start_time.timestamp() * 1000),
            endTime=int(end_time.timestamp() * 1000),
            filterPattern=search_pattern,
            limit=20,
        )
        events = resp.get("events", [])
        events.sort(key=lambda x: x["timestamp"], reverse=True)
        print(f"Found {len(events)} logs in datapoint period")
        return events[:10]
    except Exception as e:
        print(f"Error fetching logs from datapoint period: {e}")
        return []


def generate_email_content(
    alarm_name: str,
    alarm_description: str,
    timestamp: str,
    reason: str,
    error_logs: List[Dict[str, Any]],
    log_group_name: str,
    search_method: str = "datapoint_period",
    old_state: Optional[str] = None,
    new_state: Optional[str] = None,
    alarm_arn: Optional[str] = None,
) -> Tuple[str, str]:
    region_code = os.environ.get("AWS_REGION", "ap-northeast-1")
    region_long = {"ap-northeast-1": "Asia Pacific (Tokyo)"}.get(region_code, region_code)

    try:
        sts = boto3.client("sts")
        account_id = sts.get_caller_identity().get("Account", "unknown")
    except Exception:
        account_id = "unknown"

    subject = f"ALARM: \"{alarm_name}\" in {region_long}"

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

    body_extra = "\n【検出されたエラーログ（追加情報）】\n"
    if error_logs:
        body_extra += f"アラーム発生のメトリクス期間（5分間）で {len(error_logs)} 件のエラーが検出されました:\n\n"
        for i, ev in enumerate(error_logs[:5], 1):
            log_time = datetime.fromtimestamp(ev["timestamp"] / 1000)
            message = ev.get("message", "")
            if len(message) > 300:
                message = message[:300] + "..."
            body_extra += f"{i}. {log_time.strftime('%Y-%m-%d %H:%M:%S')}\n   {message}\n\n"
        if len(error_logs) > 5:
            body_extra += f"... 他 {len(error_logs) - 5} 件のエラーログがあります\n\n"
    else:
        body_extra += "詳細なエラーログの取得に失敗しました。\n\n"

    import urllib.parse
    encoded_alarm_name = urllib.parse.quote(alarm_name, safe="")
    alarm_console_link = (
        "View this alarm in the AWS Management Console:\n"
        f"https://console.aws.amazon.com/cloudwatch/home?region={region_code}#alarmsV2:alarm/{encoded_alarm_name}\n\n"
    )

    # Threshold and actions blocks (best-effort)
    try:
        cw = boto3.client("cloudwatch")
        resp = cw.describe_alarms(AlarmNames=[alarm_name])
        if resp.get("MetricAlarms"):
            al = resp["MetricAlarms"][0]
            comp = al.get("ComparisonOperator")
            thr = al.get("Threshold")
            evalp = al.get("EvaluationPeriods")
            d2a = al.get("DatapointsToAlarm")
            period = al.get("Period")
            n_dp = d2a if d2a is not None else evalp
            if comp and thr is not None and n_dp is not None and period is not None:
                sentence = (
                    f"- The alarm is in the ALARM state when the metric is {comp} {thr} "
                    f"for {n_dp} datapoints within {period} seconds.\n\n"
                )
            else:
                sentence = "- The alarm is in the ALARM state when the metric crosses the configured threshold.\n\n"
            threshold_block = "Threshold:\n" + sentence

            ns = al.get("Namespace")
            mn = al.get("MetricName")
            stat = al.get("Statistic") or al.get("ExtendedStatistic")
            unit = al.get("Unit")
            tmd = al.get("TreatMissingData")
            dims = al.get("Dimensions", [])
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

            def _fmt_actions(actions):
                return ", ".join(actions) if actions else "None"

            sca_lines = [
                "State Change Actions:",
                f"- OK: {_fmt_actions(al.get('OKActions'))}",
                f"- ALARM: {_fmt_actions(al.get('AlarmActions'))}",
                f"- INSUFFICIENT_DATA: {_fmt_actions(al.get('InsufficientDataActions'))}",
            ]
            state_change_actions_block = "\n".join(sca_lines) + "\n\n"
        else:
            threshold_block = "Threshold:\n- The alarm is in the ALARM state when the metric crosses the configured threshold.\n\n"
            monitored_metric_block = "Monitored Metric:\n- (not available)\n\n"
            state_change_actions_block = (
                "State Change Actions:\n- OK: None\n- ALARM: None\n- INSUFFICIENT_DATA: None\n\n"
            )
    except Exception:
        threshold_block = "Threshold:\n- The alarm is in the ALARM state when the metric crosses the configured threshold.\n\n"
        monitored_metric_block = "Monitored Metric:\n- (not available)\n\n"
        state_change_actions_block = (
            "State Change Actions:\n- OK: None\n- ALARM: None\n- INSUFFICIENT_DATA: None\n\n"
        )

    caution_block = (
        "【重要】購読解除に関する注意\n"
        "本メールの末尾に表示される Amazon SNS の unsubscribe リンクをクリックすると、"
        "本アラートメールが届かなくなります。運用に支障が出るため、承認を得た場合のみ実施してください。\n\n"
    )

    body = header + body_extra + alarm_console_link + details + "\n" + threshold_block + monitored_metric_block + state_change_actions_block + caution_block
    return subject, body


def send_notification(sns_topic_arn: str, subject: str, body: str) -> None:
    sns_client = boto3.client("sns")
    resp = sns_client.publish(TopicArn=sns_topic_arn, Subject=subject, Message=body)
    print(f"Notification sent successfully. MessageId: {resp['MessageId']}")


def process_alarm_event(alarm_data: Dict[str, Any]) -> None:
    email_sns_topic_arn = os.environ.get("EMAIL_SNS_TOPIC_ARN")
    if not email_sns_topic_arn:
        raise ValueError("EMAIL_SNS_TOPIC_ARN environment variable not set")

    if "AlarmName" not in alarm_data:
        raise ValueError("Invalid alarm message: missing 'AlarmName'")

    alarm_name = alarm_data.get("AlarmName", "Unknown")
    alarm_description = alarm_data.get("AlarmDescription", "")
    new_state = alarm_data.get("NewStateValue", "UNKNOWN")
    reason = alarm_data.get("NewStateReason", "")
    timestamp = alarm_data.get("StateChangeTime", datetime.now().isoformat())
    old_state = alarm_data.get("OldStateValue", "UNKNOWN")
    alarm_arn = alarm_data.get("AlarmArn", "unknown")

    print(f"Processing alarm: {alarm_name}, State: {new_state}")
    if new_state != "ALARM":
        print("State is not ALARM. Skipping.")
        return

    info = get_log_group_info_from_trigger(alarm_data)
    log_group_name = info["log_group_name"]
    filter_pattern = normalize_filter_pattern(info.get("filter_pattern", ""))
    print(f"Resolved from Trigger - Log Group: {log_group_name}")
    print(f"Resolved from Trigger - Filter Pattern: {filter_pattern}")

    # Extract datapoint timestamp (required)
    dp_ts = extract_datapoint_timestamp_from_reason(reason)
    print(f"Extracted datapoint timestamp: {dp_ts}")
    if not dp_ts:
        raise ValueError("Failed to extract datapoint timestamp from alarm reason")

    # Fetch logs for the datapoint window
    error_logs = get_logs_from_datapoint_period(log_group_name, filter_pattern, dp_ts)
    for i, log in enumerate(error_logs[:3]):
        print(f"Log {i+1}: {log.get('message', '')[:100]}...")

    subject, body = generate_email_content(
        alarm_name,
        alarm_description,
        timestamp,
        reason,
        error_logs,
        log_group_name,
        search_method="datapoint_period",
        old_state=old_state,
        new_state=new_state,
        alarm_arn=alarm_arn,
    )
    print(f"Email subject: {subject}")
    print(f"Email body preview: {body[:500]}...")

    send_notification(email_sns_topic_arn, subject, body)


def lambda_handler(event, context):
    print("=== LAMBDA FUNCTION STARTED ===")
    print(f"Event type: {type(event)}")
    print(f"Event keys: {list(event.keys()) if isinstance(event, dict) else 'Not a dict'}")
    print("=== EVENT RECEIVED ===")
    print(json.dumps(event, indent=2, default=str))

    # Only accept SNS events
    if not (isinstance(event, dict) and "Records" in event):
        print("Unsupported event: expected SNS Records. Aborting.")
        raise ValueError("Unsupported event source. This function must be invoked via SNS.")

    email_sns_topic_arn = os.environ.get("EMAIL_SNS_TOPIC_ARN")
    print(f"EMAIL_SNS_TOPIC_ARN: {email_sns_topic_arn}")
    if not email_sns_topic_arn:
        raise ValueError("EMAIL_SNS_TOPIC_ARN environment variable not set")

    for i, record in enumerate(event["Records"]):
        print(f"Record {i}: EventSource = {record.get('EventSource', 'Unknown')}")
        if record.get("EventSource") != "aws:sns":
            print(f"Unknown event source: {record.get('EventSource')}")
            continue
        msg = json.loads(record["Sns"]["Message"]) if isinstance(record.get("Sns", {}), dict) else {}
        process_alarm_event(msg)

    print("=== FUNCTION COMPLETED SUCCESSFULLY ===")
    return {"statusCode": 200, "body": json.dumps({"message": "Error notification processed successfully"})}
