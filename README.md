# AWS News AI Summarizer

This project uses AWS services to create a news aggregation and summarization application. It collects news from various RSS feeds, extracts content from articles, and uses AWS Bedrock to generate concise summaries that are delivered to Slack.

## Architecture

The application consists of the following components:

1. **News Collector Lambda**: Fetches news from RSS feeds, extracts content, and stores it in DynamoDB or S3
2. **News Processor Lambda**: Processes unprocessed news articles using AWS Bedrock for summarization
3. **Storage**: Uses either DynamoDB or S3 for storing articles and their summaries
4. **Notifications**: Sends summarized news to Slack via webhooks (with SNS as fallback)
5. **Scheduling**: Uses EventBridge to run the collector on a schedule
6. **API**: Provides API Gateway endpoints for manual triggering

## Prerequisites

- AWS Account with access to AWS Bedrock
- Terraform v1.0.0+
- Python 3.9+
- pip package manager
- AWS CLI configured with appropriate permissions
- Slack workspace with permission to create webhooks

## Setup Instructions

### 1. Clone the repository

```bash
git clone <repository-url>
cd news-ai-summarizer
```

### 2. Set up Slack Webhook

1. Go to your Slack workspace
2. Create a new channel or select an existing one to receive notifications
3. From the Slack API Apps page (https://api.slack.com/apps):
   - Create a New App
   - Select "From scratch"
   - Name it "AWS News AI Summarizer" (or your preferred name)
   - Select your workspace
4. In the app settings, go to "Incoming Webhooks" and turn the feature on
5. Click "Add New Webhook to Workspace"
6. Select the channel where you want to post notifications
7. Copy the Webhook URL for use in the next step

### 3. Update configuration (if needed)

Edit the following files to customize the project:

- `terraform/variables.tf`: Update default values for region, Bedrock model, and set your Slack webhook URL
- `lambda/news_collector/lambda_function.py`: Modify NEWS_SOURCES to add/remove news sources
- `lambda/news_processor/lambda_function.py`: Customize summarization prompts if needed

### 4. Build Lambda packages

Run the build script to create Lambda packages:

```bash
./scripts/build_lambda_packages.sh
```

This will:
- Create a Lambda layer with dependencies
- Package the news_collector Lambda function
- Package the news_processor Lambda function

### 5. Deploy with Terraform

Initialize and apply the Terraform configuration:

```bash
cd terraform
terraform init
terraform plan
terraform apply
```

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

### Output Language

You can choose the language for your summaries by setting the `OUTPUT_LANGUAGE` environment variable:

- `en`: English (default)
- `ja`: Japanese

### Notification Method

- Primary: Slack Webhook
- Fallback: Amazon SNS (if Slack webhook fails)

### SNS-to-Slack Integration Option

This project includes two ways to integrate with Slack:

1. **Direct Integration** (Default): The news_processor Lambda function sends notifications directly to Slack using webhooks.

2. **SNS-to-Slack Lambda** (Optional): You can deploy a separate Lambda function that subscribes to the SNS topic and forwards messages to Slack.

To deploy the SNS-to-Slack Lambda function:

```bash
cd terraform
terraform apply -var="deploy_sns_to_slack=true"
```

This architecture is useful when:
- You want to add other subscribers to the SNS topic
- You're already using SNS for other workflows
- You prefer the decoupled architecture pattern

## Slack Message Format

The Slack notifications include:
- A header with the date and summary title
- Article title and source
- Detailed article summary (truncated if very long)
- Link to the full announcement when available

## Cleaning Up

To remove all resources created by this project:

```bash
cd terraform
terraform destroy
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.