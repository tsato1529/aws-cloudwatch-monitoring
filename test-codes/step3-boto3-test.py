import json
import os
import boto3

def lambda_handler(event, context):
    print("=== TEST WITH BOTO3 ===")
    print(f"Event received: {json.dumps(event, default=str)}")
    print(f"EMAIL_SNS_TOPIC_ARN: {os.environ.get('EMAIL_SNS_TOPIC_ARN')}")
    
    try:
        sns_client = boto3.client('sns')
        print("boto3 SNS client created successfully")
    except Exception as e:
        print(f"boto3 error: {e}")
    
    try:
        logs_client = boto3.client('logs')
        print("boto3 CloudWatch Logs client created successfully")
    except Exception as e:
        print(f"logs client error: {e}")
    
    print("=== TEST COMPLETED ===")
    
    return {
        "statusCode": 200,
        "body": json.dumps("Test successful")
    }