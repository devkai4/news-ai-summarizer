import boto3
import json
import logging
import os
import urllib.request
import urllib.parse

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Slack Webhook URL - environment variable
SLACK_WEBHOOK_URL = os.environ['SLACK_WEBHOOK_URL']

def lambda_handler(event, context):
    """Lambda function to send SNS messages to Slack"""
    logger.info("Received event: " + json.dumps(event))
    
    # Extract SNS message
    message = event['Records'][0]['Sns']['Message']
    subject = event['Records'][0]['Sns']['Subject']
    
    try:
        # Try to parse message as JSON
        message_data = json.loads(message)
        # Check if this is the lambda-specific format
        if isinstance(message_data, str):
            # This might be the lambda field from our SNS message
            message_data = json.loads(message_data)
        
        formatted_message = format_message(message_data, subject)
    except Exception as e:
        logger.info(f"Message is not JSON formatted or has unexpected format: {e}")
        # If not JSON or not in expected format, treat as plain text
        formatted_message = {
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": subject or "AWS News Summary"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": message
                    }
                }
            ]
        }
    
    # Send to Slack
    response = post_to_slack(formatted_message)
    
    return {
        'statusCode': 200,
        'body': json.dumps('Message sent to Slack!')
    }

def format_message(message_data, subject):
    """Format the SNS message as a Slack message with blocks"""
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": subject or "AWS News Summary"
            }
        }
    ]
    
    # Determine if message_data is an array of articles or something else
    if isinstance(message_data, list):
        articles = message_data
    elif isinstance(message_data, dict) and 'articles' in message_data:
        articles = message_data['articles']
    else:
        # Just display the raw data if it doesn't match expected format
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": json.dumps(message_data, ensure_ascii=False, indent=2)
            }
        })
        return {"blocks": blocks}
    
    # Add each article as blocks
    for article in articles:
        title = article.get('title', 'No Title')
        source = article.get('source', 'Unknown Source')
        summary = article.get('summary', 'No summary available')
        link = article.get('link', '#')
        
        # Add a divider
        blocks.append({"type": "divider"})
        
        # Add title and source
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{title}*\n_Source: {source}_"
            }
        })
        
        # Add summary (truncate if too long for Slack)
        if len(summary) > 2900:
            summary = summary[:2900] + "..."
            
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": summary
            }
        })
        
        # Add link if available
        if link and link != '#':
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"<{link}|Read Full Announcement>"
                }
            })
    
    return {"blocks": blocks}

def post_to_slack(message):
    """Post message to Slack webhook"""
    data = json.dumps(message).encode('utf-8')
    req = urllib.request.Request(
        SLACK_WEBHOOK_URL,
        data=data,
        headers={'Content-Type': 'application/json'}
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            return response.read()
    except Exception as e:
        logger.error(f"Error posting to Slack: {e}")
        raise