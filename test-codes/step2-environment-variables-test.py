import json
import os

def lambda_handler(event, context):
    print("=== TEST WITH ENVIRONMENT VARIABLES ===")
    print(f"Event received: {json.dumps(event, default=str)}")
    print(f"EMAIL_SNS_TOPIC_ARN: {os.environ.get('EMAIL_SNS_TOPIC_ARN')}")
    print("=== TEST COMPLETED ===")
    
    return {
        "statusCode": 200,
        "body": json.dumps("Test successful")
    }