import json
import os
import uuid
import datetime
import feedparser
import requests
from bs4 import BeautifulSoup
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

# News sources - RSS feeds
NEWS_SOURCES = [
    {
        'name': 'BBC News',
        'url': 'http://feeds.bbci.co.uk/news/world/rss.xml',
        'language': 'en'
    },
    {
        'name': 'Reuters',
        'url': 'https://www.reutersagency.com/feed/?best-topics=tech&post_type=best',
        'language': 'en'
    },
    {
        'name': 'NHK News',
        'url': 'https://www3.nhk.or.jp/rss/news/cat0.xml',
        'language': 'ja'
    },
    {
        'name': 'Nikkei',
        'url': 'https://www.nikkei.com/rss/index.xml',
        'language': 'ja'
    }
]

def extract_article_content(url, language):
    """Extract article content from URL"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Remove script and style elements
        for script in soup(['script', 'style', 'meta', 'noscript']):
            script.decompose()
            
        # Get text from paragraph elements
        paragraphs = soup.find_all('p')
        content = ' '.join([p.get_text().strip() for p in paragraphs if len(p.get_text().strip()) > 100])
        
        # If no long paragraphs found, try to get all text
        if not content:
            content = soup.get_text().strip()
            
        return content
    except Exception as e:
        print(f"Error extracting content from {url}: {str(e)}")
        return ""

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
    """Collect articles from RSS feeds"""
    collected_articles = []
    
    for source in NEWS_SOURCES:
        try:
            # Parse RSS feed
            feed = feedparser.parse(source['url'])
            
            # Process each entry
            for entry in feed.entries[:5]:  # Get the latest 5 articles
                # Generate unique ID
                article_id = str(uuid.uuid4())
                
                # Get publication date
                if hasattr(entry, 'published_parsed'):
                    pub_date = datetime.datetime(*entry.published_parsed[:6]).isoformat()
                else:
                    pub_date = datetime.datetime.now().isoformat()
                    
                # Extract domain from the link
                domain = urlparse(entry.link).netloc
                
                # Extract article content
                content = extract_article_content(entry.link, source['language'])
                
                # Create article data
                article_data = {
                    'id': article_id,
                    'title': entry.title,
                    'link': entry.link,
                    'published_date': pub_date,
                    'source': source['name'],
                    'language': source['language'],
                    'domain': domain,
                    'summary': entry.summary if hasattr(entry, 'summary') else "",
                    'content': content,
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
                    'source': source['name']
                })
                
        except Exception as e:
            print(f"Error processing source {source['name']}: {str(e)}")
    
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