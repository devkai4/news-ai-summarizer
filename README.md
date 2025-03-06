# AWS News AI Summarizer

This project uses AWS services to create a news aggregation and summarization application. It collects news from various RSS feeds, extracts content from articles, and uses AWS Bedrock to generate concise summaries.

## Architecture

The application consists of the following components:

1. **News Collector Lambda**: Fetches news from RSS feeds, extracts content, and stores it in DynamoDB or S3
2. **News Processor Lambda**: Processes unprocessed news articles using AWS Bedrock for summarization
3. **Storage**: Uses either DynamoDB or S3 for storing articles and their summaries
4. **Notifications**: Sends summarized news via Amazon SES (email) or SNS (fallback)
5. **Scheduling**: Uses EventBridge to run the collector on a schedule
6. **API**: Provides API Gateway endpoints for manual triggering

## Prerequisites

- AWS Account with access to AWS Bedrock
- Terraform v1.0.0+
- Python 3.9+
- pip package manager
- AWS CLI configured with appropriate permissions

## Setup Instructions

### 1. Clone the repository

```bash
git clone <repository-url>
cd news-ai-summarizer
```

### 2. Update configuration (if needed)

Edit the following files to customize the project:

- `terraform/variables.tf`: Update default values for region, Bedrock model, etc.
- `lambda/news_collector/lambda_function.py`: Modify NEWS_SOURCES to add/remove news sources
- `lambda/news_processor/lambda_function.py`: Customize summarization prompts if needed

### 3. Build Lambda packages

Run the build script to create Lambda packages:

```bash
./scripts/build_lambda_packages.sh
```

This will:
- Create a Lambda layer with dependencies
- Package the news_collector Lambda function
- Package the news_processor Lambda function

### 4. Deploy with Terraform

Initialize and apply the Terraform configuration:

```bash
cd terraform
terraform init
terraform plan
terraform apply
```

### 5. Configure notification email

If using SES for email notifications:

1. Verify your email in the AWS SES console
2. Update the NOTIFICATION_EMAIL environment variable in the Lambda function

## Usage

### Automatic News Collection

By default, the news collector runs daily at midnight UTC to fetch news articles.

### Manual Triggering

You can manually trigger the functions using the API Gateway endpoints:

1. **Collect News**: Send a POST request to the /collect endpoint
2. **Process News**: Send a POST request to the /process endpoint

Example using curl:

```bash
curl -X POST https://<api-id>.execute-api.<region>.amazonaws.com/prod/collect
curl -X POST https://<api-id>.execute-api.<region>.amazonaws.com/prod/process
```

## Customization Options

### Storage Type

You can choose between two storage options by setting the `STORAGE_TYPE` environment variable:

- `dynamodb`: Uses DynamoDB table for storing articles (default)
- `s3`: Uses S3 bucket for storing articles

### Bedrock Model

The default model is Claude 3.5 Sonnet, but you can change it by updating the `BEDROCK_MODEL_ID` environment variable.

### Notification Method

- Primary: Amazon SES (email)
- Fallback: Amazon SNS (if SES fails)

## Cleaning Up

To remove all resources created by this project:

```bash
cd terraform
terraform destroy
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.