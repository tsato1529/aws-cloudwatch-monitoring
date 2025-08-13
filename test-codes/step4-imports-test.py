import json
import os
import boto3
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

def handler(event, context):
    print("=== TEST WITH ALL IMPORTS ===")
    print(f"Event received: {json.dumps(event, default=str)}")
    print(f"EMAIL_SNS_TOPIC_ARN: {os.environ.get('EMAIL_SNS_TOPIC_ARN')}")
    
    try:
        sns_client = boto3.client('sns')
        print("boto3 SNS client created successfully")
    except Exception as e:
        print(f"boto3 SNS error: {e}")
    
    try:
        logs_client = boto3.client('logs')
        print("boto3 CloudWatch Logs client created successfully")
    except Exception as e:
        print(f"logs client error: {e}")
    
    try:
        cloudwatch = boto3.client('cloudwatch')
        print("boto3 CloudWatch client created successfully")
    except Exception as e:
        print(f"cloudwatch client error: {e}")
    
    # Test datetime and re modules
    try:
        current_time = datetime.now()
        print(f"Current time: {current_time}")
        
        test_pattern = r'\d+'
        test_match = re.search(test_pattern, "test123")
        print(f"Regex test successful: {test_match.group() if test_match else 'No match'}")
    except Exception as e:
        print(f"datetime/re error: {e}")
    
    print("=== TEST COMPLETED ===")
    
    return {
        "statusCode": 200,
        "body": json.dumps("All imports test successful")
    }