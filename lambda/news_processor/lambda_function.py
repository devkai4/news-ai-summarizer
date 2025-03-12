import json
import os
import boto3
import datetime
import uuid
import urllib.request
import urllib.parse
import time
import random
from botocore.exceptions import ClientError

# Environment variables
STORAGE_TYPE = os.environ.get('STORAGE_TYPE', 'dynamodb')
NEWS_BUCKET_NAME = os.environ.get('NEWS_BUCKET_NAME')
NEWS_TABLE_NAME = os.environ.get('NEWS_TABLE_NAME')
BEDROCK_MODEL_ID = os.environ.get('BEDROCK_MODEL_ID', 'anthropic.claude-3-5-sonnet-20241022-v2:0')
SLACK_WEBHOOK_URL = os.environ.get('SLACK_WEBHOOK_URL')
SNS_TOPIC_ARN = os.environ.get('SNS_TOPIC_ARN')
OUTPUT_LANGUAGE = os.environ.get('OUTPUT_LANGUAGE', 'ja')  # Default to Japanese, can be set to 'en' for English
MAX_RETRIES = int(os.environ.get('MAX_RETRIES', '8'))  # Increase the number of retries
BATCH_SIZE = int(os.environ.get('BATCH_SIZE', '1'))  # Limit the number of articles processed at once

# Initialize AWS services
bedrock_runtime = boto3.client('bedrock-runtime')
s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
sns_client = boto3.client('sns')
news_table = dynamodb.Table(NEWS_TABLE_NAME) if STORAGE_TYPE == 'dynamodb' else None

def get_unprocessed_articles_from_dynamodb():
    """Get unprocessed articles from DynamoDB"""
    try:
        response = news_table.scan(
            FilterExpression='#proc = :processed_val AND #src = :source_val',
            ExpressionAttributeNames={
                '#proc': 'processed',
                '#src': 'source'
            },
            ExpressionAttributeValues={
                ':processed_val': False,
                ':source_val': 'AWS Announcements'
            }
        )

        return response.get('Items', [])
    except Exception as e:
        print(f"Error getting articles from DynamoDB: {str(e)}")
        return []

def get_unprocessed_articles_from_s3():
    """Get unprocessed articles from S3"""
    try:
        articles = []

        # List objects in the bucket with prefix
        paginator = s3_client.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=NEWS_BUCKET_NAME, Prefix='articles/AWS Announcements/')

        for page in pages:
            if 'Contents' in page:
                for obj in page['Contents']:
                    # Get object content
                    response = s3_client.get_object(Bucket=NEWS_BUCKET_NAME, Key=obj['Key'])
                    article_data = json.loads(response['Body'].read().decode('utf-8'))

                    # Check if article is unprocessed
                    if not article_data.get('processed', False):
                        articles.append(article_data)

        return articles
    except Exception as e:
        print(f"Error getting articles from S3: {str(e)}")
        return []

def summarize_article_with_bedrock(article_data, language='en'):
    """Summarize article using Bedrock with optional translation and robust retry mechanism"""
    # Initialize retry counter
    retry_count = 0
    base_delay = 1  # Base delay in seconds

    while retry_count <= MAX_RETRIES:
        try:
            # Prepare content for summarization
            content = article_data.get('content', '')
            title = article_data.get('title', '')
            source = article_data.get('source', '')
            link = article_data.get('link', '')

            # Skip if no content
            if not content:
                return "No content available for summarization."

            # Prepare prompt based on requested output language
            if language == 'ja':
                prompt = f"""Article Title: {title}
Source: {source}
Link: {link}

Article Content:
{content}

This is an AWS announcement. Please provide a detailed analysis of this AWS service or feature announcement in Japanese.
Please explain the following aspects in depth:
1. Overview and purpose of the announced service or feature
2. Main capabilities, features, and specific benefits they bring to businesses and developers
3. Available regions and deployment plans
4. Detailed pricing structure and cost information
5. Case studies or recommended usage scenarios (if mentioned)

Please structure your response in paragraphs rather than bullet points, providing detailed explanations for each topic. Include technical characteristics and advantages specifically, offering as comprehensive information as possible.
At the end, please include the following URL for reference: {link}"""
            else:
                prompt = f"""Article Title: {title}
Source: {source}
Link: {link}

Article Content:
{content}

This is an AWS announcement. Please provide a comprehensive analysis of this AWS service or feature announcement in detail.
Please explain the following aspects in depth:
1. Overview and purpose of the announced service or feature
2. Main capabilities, features, and specific benefits they bring to businesses and developers
3. Available regions and deployment plans
4. Detailed pricing structure and cost information
5. Case studies or recommended usage scenarios (if mentioned)

Please structure your response in paragraphs rather than bullet points, providing detailed explanations for each topic. Include technical characteristics and advantages specifically, offering as comprehensive information as possible.
At the end, please include the following URL for reference: {link}"""

            # Prepare request body based on model
            if "claude" in BEDROCK_MODEL_ID.lower():
                request_body = {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 1000,
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ]
                }
            else:  # Default for other models
                request_body = {
                    "prompt": prompt,
                    "max_tokens": 1000
                }

            # Invoke Bedrock model
            response = bedrock_runtime.invoke_model(
                modelId=BEDROCK_MODEL_ID,
                body=json.dumps(request_body)
            )

            # Parse response based on model
            response_body = json.loads(response['body'].read())

            if "claude" in BEDROCK_MODEL_ID.lower():
                summary = response_body['content'][0]['text']
            else:  # Default for other models
                summary = response_body.get('completion', '')

            return summary

        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')

            # Retry for ThrottlingException or ServiceQuotaExceeded
            if error_code in ["ThrottlingException", "ServiceQuotaExceeded", "TooManyRequestsException"]:
                retry_count += 1

                if retry_count > MAX_RETRIES:
                    print(f"Maximum retries reached ({MAX_RETRIES}). Giving up on article: {article_data.get('title')}")
                    return f"Error generating summary after {MAX_RETRIES} retries: {str(e)}"

                # Apply exponential backoff with jitter (randomization)
                jitter = random.uniform(1, 5)  # Random value between 1 and 5 seconds
                delay = (2 ** retry_count) * base_delay + jitter

                print(f"Bedrock API throttled. Retry {retry_count}/{MAX_RETRIES} after {delay:.2f} seconds")
                time.sleep(delay)
            else:
                # Fail immediately for other errors
                print(f"Error summarizing with Bedrock: {str(e)}")
                return f"Error generating summary: {str(e)}"

        except Exception as e:
            print(f"Unexpected error summarizing with Bedrock: {str(e)}")
            return f"Error generating summary: {str(e)}"

def update_article_in_dynamodb(article_id, summary):
    """Update article in DynamoDB with summary"""
    try:
        news_table.update_item(
            Key={'id': article_id},
            UpdateExpression='SET summary = :summary, #proc = :processed_val, processed_at = :processed_at',
            ExpressionAttributeNames={
                '#proc': 'processed'
            },
            ExpressionAttributeValues={
                ':summary': summary,
                ':processed_val': True,
                ':processed_at': datetime.datetime.now().isoformat()
            }
        )
        return True
    except Exception as e:
        print(f"Error updating article in DynamoDB: {str(e)}")
        return False

def update_article_in_s3(article_data, summary):
    """Update article in S3 with summary"""
    try:
        article_id = article_data['id']
        source = article_data['source']
        s3_key = f"articles/{source}/{article_id}.json"

        # Update article data
        article_data['summary'] = summary
        article_data['processed'] = True
        article_data['processed_at'] = datetime.datetime.now().isoformat()

        # Save updated article
        s3_client.put_object(
            Bucket=NEWS_BUCKET_NAME,
            Key=s3_key,
            Body=json.dumps(article_data, ensure_ascii=False),
            ContentType='application/json'
        )

        return True
    except Exception as e:
        print(f"Error updating article in S3: {str(e)}")
        return False

def send_slack_notification(articles_with_summaries):
    """Send Slack notification with article summaries"""
    try:
        if not SLACK_WEBHOOK_URL:
            print("No Slack webhook URL configured")
            return False

        # Prepare notification content with language-specific headers
        if OUTPUT_LANGUAGE == 'ja':
            header_text = f"AWS News Summary for {datetime.datetime.now().strftime('%Y-%m-%d')}"
            intro_text = "Here are today's AWS announcement summaries:"
            read_more_text = "Read Full Announcement"
        else:
            header_text = f"AWS News Summaries for {datetime.datetime.now().strftime('%Y-%m-%d')}"
            intro_text = "Here are your daily AWS announcement summaries:"
            read_more_text = "Read Full Announcement"

        # Create Slack message with blocks
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": header_text
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": intro_text
                }
            }
        ]

        # Add each article summary as blocks
        for article in articles_with_summaries:
            title = article.get('title', 'No Title')
            source = article.get('source', 'Unknown Source')
            summary = article.get('summary', 'No summary available')
            link = article.get('link', '#')

            # Add a divider between articles
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
            # Slack blocks have a text limit of 3000 characters
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
                        "text": f"<{link}|{read_more_text}>"
                    }
                })

        # Prepare the Slack message payload
        slack_message = {
            "blocks": blocks
        }

        # Send to Slack
        try:
            data = json.dumps(slack_message).encode('utf-8')
            req = urllib.request.Request(
                SLACK_WEBHOOK_URL,
                data=data,
                headers={'Content-Type': 'application/json'}
            )

            with urllib.request.urlopen(req) as response:
                print(f"Slack notification sent successfully: {response.read().decode('utf-8')}")
                return True

        except Exception as e:
            print(f"Error sending Slack notification: {str(e)}")

            # If Slack fails, try SNS as fallback
            if SNS_TOPIC_ARN:
                print("Falling back to SNS notification")
                return send_sns_notification(articles_with_summaries)

            return False

    except Exception as e:
        print(f"Error preparing Slack notification: {str(e)}")
        return False

def send_sns_notification(articles_with_summaries):
    """Send SNS notification with article summaries"""
    try:
        if not SNS_TOPIC_ARN:
            print("No SNS topic ARN configured")
            return False

        # Prepare notification content with language-specific subjects
        if OUTPUT_LANGUAGE == 'ja':
            subject = f"AWS News Summary - {datetime.datetime.now().strftime('%Y-%m-%d')}"
            message = f"AWS News Summary for {datetime.datetime.now().strftime('%Y-%m-%d')}\n\n"
        else:
            subject = f"AWS News Summary - {datetime.datetime.now().strftime('%Y-%m-%d')}"
            message = f"AWS News Summaries for {datetime.datetime.now().strftime('%Y-%m-%d')}\n\n"

        # Add each article summary
        for article in articles_with_summaries:
            title = article.get('title', 'No Title')
            source = article.get('source', 'Unknown Source')
            summary = article.get('summary', 'No summary available')
            link = article.get('link', '#')

            message += f"{title}\n"
            message += f"Source: {source}\n"
            message += f"{summary}\n"

            # Add link explicitly in the message body if available
            if link and link != '#':
                if OUTPUT_LANGUAGE == 'ja':
                    message += f"More information: {link}\n\n"
                else:
                    message += f"More information: {link}\n\n"
            else:
                message += "\n"

        # Format the articles as JSON for better compatibility with Lambda functions
        # that may subscribe to this topic (like a Slack notification Lambda)
        articles_json = []
        for article in articles_with_summaries:
            articles_json.append({
                "title": article.get('title', 'No Title'),
                "source": article.get('source', 'Unknown Source'),
                "summary": article.get('summary', 'No summary available'),
                "link": article.get('link', '#')
            })

        # Send notification with both text and structured format
        response = sns_client.publish(
            TopicArn=SNS_TOPIC_ARN,
            Message=json.dumps({
                "default": message,
                "email": message,
                "lambda": json.dumps(articles_json)
            }),
            Subject=subject,
            MessageStructure="json"  # This enables sending different message formats to different endpoints
        )

        print(f"SNS notification sent successfully: {response}")
        return True
    except Exception as e:
        print(f"Error sending SNS notification: {str(e)}")
        return False

def process_articles():
    """Process unprocessed articles with improved batch processing"""
    articles_with_summaries = []

    # Get unprocessed articles based on storage type
    if STORAGE_TYPE == 's3':
        unprocessed_articles = get_unprocessed_articles_from_s3()
    else:  # default to dynamodb
        unprocessed_articles = get_unprocessed_articles_from_dynamodb()

    total_articles = len(unprocessed_articles)
    print(f"Found {total_articles} unprocessed AWS announcements")
    print(f"Output language set to: {OUTPUT_LANGUAGE}")
    print(f"Processing in batches of {BATCH_SIZE}")

    # Split articles for batch processing
    for i in range(0, total_articles, BATCH_SIZE):
        batch = unprocessed_articles[i:i+BATCH_SIZE]
        print(f"Processing batch {i//BATCH_SIZE + 1}/{(total_articles + BATCH_SIZE - 1)//BATCH_SIZE} ({len(batch)} articles)")

        # Process each article in the current batch
        for article in batch:
            article_id = article.get('id')
            title = article.get('title', 'No Title')
            print(f"Processing article: {title}")

            # Summarize article in the specified language
            summary = summarize_article_with_bedrock(article, OUTPUT_LANGUAGE)

            # Update article with summary
            if STORAGE_TYPE == 's3':
                update_success = update_article_in_s3(article, summary)
            else:  # default to dynamodb
                update_success = update_article_in_dynamodb(article_id, summary)

            if update_success:
                # Add article with summary to list for notification
                article_with_summary = article.copy()
                article_with_summary['summary'] = summary
                articles_with_summaries.append(article_with_summary)
                print(f"Successfully processed article: {title}")

            # Short wait between articles in a batch
            if len(batch) > 1:
                time.sleep(0.5)

        # Wait between batches (to avoid API rate limits)
        if i + BATCH_SIZE < total_articles:
            batch_delay = random.uniform(5, 15)  # Random wait between 5-15 seconds
            print(f"Waiting {batch_delay:.2f} seconds before next batch...")
            time.sleep(batch_delay)

    # Send notification if articles were processed
    if articles_with_summaries:
        print(f"Sending notifications for {len(articles_with_summaries)} processed articles")
        # Try Slack notification first
        if SLACK_WEBHOOK_URL:
            slack_success = send_slack_notification(articles_with_summaries)
            # If Slack fails and SNS is configured, the slack function will fall back to SNS
        # If no Slack webhook is configured but SNS is, use SNS directly
        elif SNS_TOPIC_ARN:
            send_sns_notification(articles_with_summaries)

    return articles_with_summaries

def lambda_handler(event, context):
    try:
        start_time = datetime.datetime.now()
        print(f"Lambda function started at: {start_time.isoformat()}")

        # Check if this is an API Gateway event
        is_api_event = event.get('httpMethod') is not None

        # Process articles
        processed_articles = process_articles()

        end_time = datetime.datetime.now()
        duration = (end_time - start_time).total_seconds()
        print(f"Lambda function completed in {duration:.2f} seconds")

        # Prepare response
        result = {
            'statusCode': 200,
            'articles_processed': len(processed_articles),
            'articles': [
                {
                    'id': article.get('id'),
                    'title': article.get('title'),
                    'source': article.get('source')
                } for article in processed_articles
            ]
        }

        # Format response for API Gateway if needed
        if is_api_event:
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json'
                },
                'body': json.dumps(result)
            }

        return result

    except Exception as e:
        error_message = f"Error: {str(e)}"
        print(error_message)

        # Format error response for API Gateway if needed
        if event.get('httpMethod') is not None:
            return {
                'statusCode': 500,
                'headers': {
                    'Content-Type': 'application/json'
                },
                'body': json.dumps({'error': error_message})
            }

        return {'error': error_message}

# For local testing
if __name__ == "__main__":
    print(json.dumps(lambda_handler({}, None), indent=2))
