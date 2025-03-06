import json
import os
import boto3
import datetime
import uuid
from botocore.exceptions import ClientError

# Environment variables
STORAGE_TYPE = os.environ.get('STORAGE_TYPE', 'dynamodb')
NEWS_BUCKET_NAME = os.environ.get('NEWS_BUCKET_NAME')
NEWS_TABLE_NAME = os.environ.get('NEWS_TABLE_NAME')
BEDROCK_MODEL_ID = os.environ.get('BEDROCK_MODEL_ID', 'anthropic.claude-3-5-sonnet-20240620-v1:0')
NOTIFICATION_EMAIL = os.environ.get('NOTIFICATION_EMAIL')
SNS_TOPIC_ARN = os.environ.get('SNS_TOPIC_ARN')

# Initialize AWS services
bedrock_runtime = boto3.client('bedrock-runtime')
s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
ses_client = boto3.client('ses')
sns_client = boto3.client('sns')
news_table = dynamodb.Table(NEWS_TABLE_NAME) if STORAGE_TYPE == 'dynamodb' else None

def get_unprocessed_articles_from_dynamodb():
    """Get unprocessed articles from DynamoDB"""
    try:
        response = news_table.scan(
            FilterExpression='processed = :processed',
            ExpressionAttributeValues={
                ':processed': False
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
        pages = paginator.paginate(Bucket=NEWS_BUCKET_NAME, Prefix='articles/')
        
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

def summarize_article_with_bedrock(article_data):
    """Summarize article using Bedrock"""
    try:
        # Prepare content for summarization
        content = article_data.get('content', '')
        title = article_data.get('title', '')
        source = article_data.get('source', '')
        language = article_data.get('language', 'en')
        
        # Skip if no content
        if not content:
            return "No content available for summarization."
        
        # Prepare prompt based on language
        if language == 'ja':
            prompt = f"""記事のタイトル: {title}
出所: {source}

記事の内容:
{content}

上記の記事を簡潔に要約してください。要約は3〜5つの箇条書きでまとめてください。最も重要なポイントに焦点を当ててください。各ポイントは1〜2文で簡潔にまとめてください。"""
        else:
            prompt = f"""Article Title: {title}
Source: {source}

Article Content:
{content}

Summarize the above article concisely. Focus on the most important points and present them as 3-5 bullet points. Keep each point brief and to the point, with 1-2 sentences per bullet."""

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
        
    except Exception as e:
        print(f"Error summarizing with Bedrock: {str(e)}")
        return f"Error generating summary: {str(e)}"

def update_article_in_dynamodb(article_id, summary):
    """Update article in DynamoDB with summary"""
    try:
        news_table.update_item(
            Key={'id': article_id},
            UpdateExpression='SET summary = :summary, processed = :processed, processed_at = :processed_at',
            ExpressionAttributeValues={
                ':summary': summary,
                ':processed': True,
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

def send_email_notification(articles_with_summaries):
    """Send email notification with article summaries"""
    try:
        if not NOTIFICATION_EMAIL:
            print("No notification email configured")
            return False
            
        # Prepare email content
        subject = f"News Summary - {datetime.datetime.now().strftime('%Y-%m-%d')}"
        
        body_html = f"""<html>
<head>
  <style>
    body {{ font-family: Arial, sans-serif; }}
    .article {{ margin-bottom: 30px; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }}
    h2 {{ color: #333; }}
    .source {{ color: #666; font-style: italic; }}
    .summary {{ margin-top: 10px; }}
    a {{ color: #0066cc; }}
  </style>
</head>
<body>
  <h1>News Summaries for {datetime.datetime.now().strftime('%Y-%m-%d')}</h1>
  
  <p>Here are your daily news summaries:</p>
  
"""
        
        body_text = f"News Summaries for {datetime.datetime.now().strftime('%Y-%m-%d')}\n\n"
        
        # Add each article summary
        for article in articles_with_summaries:
            title = article.get('title', 'No Title')
            source = article.get('source', 'Unknown Source')
            summary = article.get('summary', 'No summary available')
            link = article.get('link', '#')
            
            body_html += f"""<div class="article">
    <h2>{title}</h2>
    <p class="source">Source: {source}</p>
    <div class="summary">{summary}</div>
    <p><a href="{link}" target="_blank">Read Full Article</a></p>
  </div>
"""
            
            body_text += f"{title}\n"
            body_text += f"Source: {source}\n"
            body_text += f"{summary}\n"
            body_text += f"Link: {link}\n\n"
            
        body_html += """</body>
</html>"""
        
        # Send email using SES
        try:
            response = ses_client.send_email(
                Source=NOTIFICATION_EMAIL,
                Destination={
                    'ToAddresses': [NOTIFICATION_EMAIL]
                },
                Message={
                    'Subject': {
                        'Data': subject
                    },
                    'Body': {
                        'Text': {
                            'Data': body_text
                        },
                        'Html': {
                            'Data': body_html
                        }
                    }
                }
            )
            return True
        except ClientError as e:
            print(f"Error sending email: {e.response['Error']['Message']}")
            
            # If SES fails, try SNS as fallback
            if SNS_TOPIC_ARN:
                send_sns_notification(articles_with_summaries)
                
            return False
            
    except Exception as e:
        print(f"Error preparing email notification: {str(e)}")
        return False

def send_sns_notification(articles_with_summaries):
    """Send SNS notification with article summaries"""
    try:
        if not SNS_TOPIC_ARN:
            print("No SNS topic ARN configured")
            return False
            
        # Prepare notification content
        subject = f"News Summary - {datetime.datetime.now().strftime('%Y-%m-%d')}"
        
        message = f"News Summaries for {datetime.datetime.now().strftime('%Y-%m-%d')}\n\n"
        
        # Add each article summary
        for article in articles_with_summaries:
            title = article.get('title', 'No Title')
            source = article.get('source', 'Unknown Source')
            summary = article.get('summary', 'No summary available')
            link = article.get('link', '#')
            
            message += f"{title}\n"
            message += f"Source: {source}\n"
            message += f"{summary}\n"
            message += f"Link: {link}\n\n"
            
        # Send notification
        response = sns_client.publish(
            TopicArn=SNS_TOPIC_ARN,
            Message=message,
            Subject=subject
        )
        
        return True
    except Exception as e:
        print(f"Error sending SNS notification: {str(e)}")
        return False

def process_articles():
    """Process unprocessed articles"""
    articles_with_summaries = []
    
    # Get unprocessed articles based on storage type
    if STORAGE_TYPE == 's3':
        unprocessed_articles = get_unprocessed_articles_from_s3()
    else:  # default to dynamodb
        unprocessed_articles = get_unprocessed_articles_from_dynamodb()
        
    print(f"Found {len(unprocessed_articles)} unprocessed articles")
    
    # Process each article
    for article in unprocessed_articles:
        article_id = article.get('id')
        
        # Summarize article
        summary = summarize_article_with_bedrock(article)
        
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
    
    # Send notification if articles were processed
    if articles_with_summaries:
        send_email_notification(articles_with_summaries)
        
    return articles_with_summaries

def lambda_handler(event, context):
    try:
        # Check if this is an API Gateway event
        is_api_event = event.get('httpMethod') is not None
        
        # Process articles
        processed_articles = process_articles()
        
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