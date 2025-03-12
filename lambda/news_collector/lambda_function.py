import json
import os
import uuid
import datetime
import feedparser
import boto3
from urllib.parse import urlparse

# Environment variables
STORAGE_TYPE = os.environ.get('STORAGE_TYPE', 'dynamodb')
NEWS_BUCKET_NAME = os.environ.get('NEWS_BUCKET_NAME')
NEWS_TABLE_NAME = os.environ.get('NEWS_TABLE_NAME')

# Initialize AWS services
s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
news_table = dynamodb.Table(NEWS_TABLE_NAME) if STORAGE_TYPE == 'dynamodb' else None

# AWS Recent Announcements RSS feed
RSS_FEED_URL = "https://aws.amazon.com/about-aws/whats-new/recent/feed/"

def save_article_to_s3(article_data):
    """Save article data to S3"""
    try:
        article_id = article_data['id']
        s3_key = f"articles/{article_data['source']}/{article_id}.json"

        s3_client.put_object(
            Bucket=NEWS_BUCKET_NAME,
            Key=s3_key,
            Body=json.dumps(article_data, ensure_ascii=False),
            ContentType='application/json'
        )

        return True
    except Exception as e:
        print(f"Error saving to S3: {str(e)}")
        return False

def save_article_to_dynamodb(article_data):
    """Save article data to DynamoDB"""
    try:
        news_table.put_item(Item=article_data)
        return True
    except Exception as e:
        print(f"Error saving to DynamoDB: {str(e)}")
        return False

def collect_articles():
    """Collect articles from AWS RSS feed"""
    collected_articles = []

    try:
        # Parse RSS feed
        feed = feedparser.parse(RSS_FEED_URL)

        # Process each entry
        for entry in feed.entries[:10]:  # Get the latest 10 articles
            # Generate unique ID
            article_id = str(uuid.uuid4())

            # Get publication date
            if hasattr(entry, 'published_parsed'):
                pub_date = datetime.datetime(*entry.published_parsed[:6]).isoformat()
            else:
                pub_date = datetime.datetime.now().isoformat()

            # Extract domain from the link
            domain = urlparse(entry.link).netloc

            # Create article data
            article_data = {
                'id': article_id,
                'title': entry.title,
                'link': entry.link,
                'published_date': pub_date,
                'source': 'AWS Announcements',
                'language': 'en',
                'domain': domain,
                'summary': entry.description if hasattr(entry, 'description') else "",
                'content': entry.description if hasattr(entry, 'description') else "",
                'processed': False,
                'created_at': datetime.datetime.now().isoformat()
            }

            # Save article according to storage type
            if STORAGE_TYPE == 's3':
                save_article_to_s3(article_data)
            else:
                save_article_to_dynamodb(article_data)

            collected_articles.append({
                'id': article_id,
                'title': entry.title,
                'source': 'AWS Announcements'
            })

    except Exception as e:
        print(f"Error processing AWS Announcements feed: {str(e)}")

    return collected_articles

def lambda_handler(event, context):
    try:
        # Check if this is an API Gateway event
        is_api_event = event.get('httpMethod') is not None

        # Collect news articles
        collected_articles = collect_articles()

        # Prepare response
        result = {
            'statusCode': 200,
            'articles_collected': len(collected_articles),
            'articles': collected_articles
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
