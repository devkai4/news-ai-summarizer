import json
import os
import boto3
import uuid

# Initialize AWS Lambda client
lambda_client = boto3.client('lambda')

def lambda_handler(event, context):
    """Handler for the async process endpoint"""
    try:
        # Check if this is an API Gateway event
        is_api_event = event.get('httpMethod') is not None

        if is_api_event:
            # Extract any parameters if needed
            # body = json.loads(event.get('body', '{}')) if event.get('body') else {}

            # Generate a unique process_id
            process_id = str(uuid.uuid4())

            # Invoke the original processor Lambda asynchronously
            response = lambda_client.invoke(
                FunctionName=os.environ.get('PROCESSOR_LAMBDA_NAME', 'news_processor'),
                InvocationType='Event',  # Asynchronous invocation
                Payload=json.dumps({
                    'process_id': process_id
                })
            )

            # Respond immediately to the API client
            return {
                'statusCode': 202,  # Accepted
                'headers': {
                    'Content-Type': 'application/json'
                },
                'body': json.dumps({
                    'message': 'Processing started. This may take a few minutes.',
                    'process_id': process_id
                })
            }
        else:
            # If not an API Gateway event, forward to the processor
            return lambda_client.invoke(
                FunctionName=os.environ.get('PROCESSOR_LAMBDA_NAME', 'news_processor'),
                InvocationType='RequestResponse',
                Payload=json.dumps(event)
            )

    except Exception as e:
        error_message = f"Error: {str(e)}"
        print(error_message)

        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json'
            },
            'body': json.dumps({'error': error_message})
        }
