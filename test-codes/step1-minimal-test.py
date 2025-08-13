import json

def lambda_handler(event, context):
    print("=== MINIMAL TEST STARTED ===")
    print(f"Event received: {json.dumps(event, default=str)}")
    print("=== MINIMAL TEST COMPLETED ===")
    
    return {
        "statusCode": 200,
        "body": json.dumps("Test successful")
    }