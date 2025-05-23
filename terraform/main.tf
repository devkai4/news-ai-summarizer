provider "aws" {
  region = "ap-northeast-1"
  # access_key = var.access_key
  # secret_key = var.secret_key
}

# IAM Role for Lambda functions
resource "aws_iam_role" "lambda_role" {
  name = "news_app_lambda_role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

# Lambda execution policy
resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Policy for S3 access
resource "aws_iam_role_policy" "lambda_s3_policy" {
  name = "lambda_s3_policy"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:ListBucket"
        ]
        Resource = [
          "${aws_s3_bucket.news_bucket.arn}",
          "${aws_s3_bucket.news_bucket.arn}/*"
        ]
      }
    ]
  })
}

# Policy for DynamoDB access
resource "aws_iam_role_policy" "lambda_dynamodb_policy" {
  name = "lambda_dynamodb_policy"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query",
          "dynamodb:Scan"
        ]
        Resource = [
          "${aws_dynamodb_table.news_table.arn}"
        ]
      }
    ]
  })
}

# Policy for Bedrock access
resource "aws_iam_role_policy" "lambda_bedrock_policy" {
  name = "lambda_bedrock_policy"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel"
        ]
        Resource = "*"
      }
    ]
  })
}

# Policy for SES access
resource "aws_iam_role_policy" "lambda_ses_policy" {
  name = "lambda_ses_policy"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ses:SendEmail",
          "ses:SendRawEmail"
        ]
        Resource = "*"
      }
    ]
  })
}

# Policy for SNS access
resource "aws_iam_role_policy" "lambda_sns_policy" {
  name = "lambda_sns_policy"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "sns:Publish"
        ]
        Resource = "*"
      }
    ]
  })
}

# S3 bucket for storing news articles
resource "aws_s3_bucket" "news_bucket" {
  bucket = "news-ai-summarizer-storage"
}

# DynamoDB table for storing news data
resource "aws_dynamodb_table" "news_table" {
  name         = "NewsArticles"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "id"

  attribute {
    name = "id"
    type = "S"
  }

  attribute {
    name = "source"
    type = "S"
  }

  attribute {
    name = "published_date"
    type = "S"
  }

  global_secondary_index {
    name            = "source-published_date-index"
    hash_key        = "source"
    range_key       = "published_date"
    projection_type = "ALL"
  }
}

# Lambda layer with dependencies
resource "aws_lambda_layer_version" "news_dependencies" {
  layer_name          = "news_dependencies"
  compatible_runtimes = ["python3.9"]
  filename            = "${path.module}/../lambda-layer.zip"
}

# Lambda function for collecting news
resource "aws_lambda_function" "news_collector" {
  function_name = "news_collector"
  role          = aws_iam_role.lambda_role.arn
  handler       = "lambda_function.lambda_handler"
  runtime       = "python3.9"
  timeout       = 300
  memory_size   = 256

  filename = "${path.module}/../news_collector.zip"

  layers = [aws_lambda_layer_version.news_dependencies.arn]

  environment {
    variables = {
      NEWS_BUCKET_NAME = aws_s3_bucket.news_bucket.bucket
      NEWS_TABLE_NAME  = aws_dynamodb_table.news_table.name
      STORAGE_TYPE     = "dynamodb" # or "s3"
    }
  }
}

# Lambda function for processing news with Bedrock
resource "aws_lambda_function" "news_processor" {
  function_name = "news_processor"
  role          = aws_iam_role.lambda_role.arn
  handler       = "lambda_function.lambda_handler"
  runtime       = "python3.9"
  timeout       = 600 # Increase timeout from 300 to 600
  memory_size   = 1024

  filename = "${path.module}/../news_processor.zip"

  layers = [aws_lambda_layer_version.news_dependencies.arn]

  environment {
    variables = {
      NEWS_BUCKET_NAME  = aws_s3_bucket.news_bucket.bucket
      NEWS_TABLE_NAME   = aws_dynamodb_table.news_table.name
      STORAGE_TYPE      = "dynamodb" # or "s3"
      BEDROCK_MODEL_ID  = "anthropic.claude-3-5-sonnet-20241022-v2:0"
      SLACK_WEBHOOK_URL = var.slack_webhook_url
      SNS_TOPIC_ARN     = aws_sns_topic.news_updates.arn
    }
  }
}

# EventBridge rule to trigger news collector (daily at 7:00 AM JST / 10:00 PM UTC)
resource "aws_cloudwatch_event_rule" "daily_news_collection" {
  name                = "daily_news_collection"
  description         = "Triggers Lambda to collect news daily at 7:00 AM Japan time"
  schedule_expression = "cron(0 22 * * ? *)"
}

# EventBridge target to Lambda
resource "aws_cloudwatch_event_target" "news_collector_target" {
  rule      = aws_cloudwatch_event_rule.daily_news_collection.name
  target_id = "news_collector"
  arn       = aws_lambda_function.news_collector.arn
}

# Lambda permission for EventBridge
resource "aws_lambda_permission" "allow_eventbridge" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.news_collector.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_news_collection.arn
}

# API Gateway for manual triggers
resource "aws_api_gateway_rest_api" "news_api" {
  name        = "news_api"
  description = "API for news summarization app"
}

# API Gateway resource for collector
resource "aws_api_gateway_resource" "collect_resource" {
  rest_api_id = aws_api_gateway_rest_api.news_api.id
  parent_id   = aws_api_gateway_rest_api.news_api.root_resource_id
  path_part   = "collect"
}

# API Gateway method for collector
resource "aws_api_gateway_method" "collect_method" {
  rest_api_id   = aws_api_gateway_rest_api.news_api.id
  resource_id   = aws_api_gateway_resource.collect_resource.id
  http_method   = "POST"
  authorization = "NONE"
}

# API Gateway integration with Lambda
resource "aws_api_gateway_integration" "collect_integration" {
  rest_api_id = aws_api_gateway_rest_api.news_api.id
  resource_id = aws_api_gateway_resource.collect_resource.id
  http_method = aws_api_gateway_method.collect_method.http_method

  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.news_collector.invoke_arn
}

# Lambda permission for API Gateway
resource "aws_lambda_permission" "api_gateway_collector" {
  statement_id  = "AllowExecutionFromAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.news_collector.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.news_api.execution_arn}/*/${aws_api_gateway_method.collect_method.http_method}${aws_api_gateway_resource.collect_resource.path}"
}

# API Gateway resource for processor
resource "aws_api_gateway_resource" "process_resource" {
  rest_api_id = aws_api_gateway_rest_api.news_api.id
  parent_id   = aws_api_gateway_rest_api.news_api.root_resource_id
  path_part   = "process"
}

# API Gateway method for processor
resource "aws_api_gateway_method" "process_method" {
  rest_api_id   = aws_api_gateway_rest_api.news_api.id
  resource_id   = aws_api_gateway_resource.process_resource.id
  http_method   = "POST"
  authorization = "NONE"
}

# API Gateway integration with Lambda
resource "aws_api_gateway_integration" "process_integration" {
  rest_api_id = aws_api_gateway_rest_api.news_api.id
  resource_id = aws_api_gateway_resource.process_resource.id
  http_method = aws_api_gateway_method.process_method.http_method

  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.news_processor.invoke_arn
}

# Lambda permission for API Gateway
resource "aws_lambda_permission" "api_gateway_processor" {
  statement_id  = "AllowExecutionFromAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.news_processor.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.news_api.execution_arn}/*/${aws_api_gateway_method.process_method.http_method}${aws_api_gateway_resource.process_resource.path}"
}

# API Gateway deployment
# API Gateway deployment
resource "aws_api_gateway_deployment" "news_api_deployment" {
  depends_on = [
    aws_api_gateway_integration.collect_integration,
    aws_api_gateway_integration.process_integration,
    aws_api_gateway_integration.process_async_integration
  ]

  rest_api_id = aws_api_gateway_rest_api.news_api.id

  # Optional: You can add a trigger to force redeployment when needed
  triggers = {
    # This will cause a redeployment each time this value changes
    redeployment = sha1(jsonencode([
      aws_api_gateway_resource.collect_resource.id,
      aws_api_gateway_resource.process_resource.id,
      aws_api_gateway_resource.process_async_resource.id,
      aws_api_gateway_method.collect_method.id,
      aws_api_gateway_method.process_method.id,
      aws_api_gateway_method.process_async_method.id,
      aws_api_gateway_integration.collect_integration.id,
      aws_api_gateway_integration.process_integration.id,
      aws_api_gateway_integration.process_async_integration.id
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }
}



# Add a separate API Gateway stage resource
resource "aws_api_gateway_stage" "prod" {
  deployment_id = aws_api_gateway_deployment.news_api_deployment.id
  rest_api_id   = aws_api_gateway_rest_api.news_api.id
  stage_name    = "prod"

  # Set longer timeout (in milliseconds) - 29 seconds is the maximum
  variables = {
    "timeout" = "29000"
  }
}

# Add API Gateway method settings for the process endpoint
resource "aws_api_gateway_method_settings" "process_settings" {
  rest_api_id = aws_api_gateway_rest_api.news_api.id
  stage_name  = aws_api_gateway_stage.prod.stage_name
  method_path = "${aws_api_gateway_resource.process_resource.path_part}/${aws_api_gateway_method.process_method.http_method}"

  settings {
    throttling_burst_limit = 5
    throttling_rate_limit  = 10
    # Remove logging and metrics settings
  }
}

# SNS Topic for news updates
resource "aws_sns_topic" "news_updates" {
  name = "news_updates"
}

# Optional SNS-to-Slack Lambda function
resource "aws_lambda_function" "sns_to_slack" {
  count         = var.deploy_sns_to_slack ? 1 : 0
  function_name = "sns_to_slack"
  role          = aws_iam_role.lambda_role.arn
  handler       = "lambda_function.lambda_handler"
  runtime       = "python3.9"
  timeout       = 60
  memory_size   = 128

  filename = "${path.module}/../lambda/sns_to_slack/lambda_function.zip"

  environment {
    variables = {
      SLACK_WEBHOOK_URL = var.slack_webhook_url
    }
  }
}

# SNS subscription for sns_to_slack Lambda
resource "aws_sns_topic_subscription" "sns_to_slack_subscription" {
  count     = var.deploy_sns_to_slack ? 1 : 0
  topic_arn = aws_sns_topic.news_updates.arn
  protocol  = "lambda"
  endpoint  = aws_lambda_function.sns_to_slack[0].arn
}

# Permission for SNS to invoke sns_to_slack Lambda
resource "aws_lambda_permission" "sns_to_slack_permission" {
  count         = var.deploy_sns_to_slack ? 1 : 0
  statement_id  = "AllowExecutionFromSNS"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.sns_to_slack[0].function_name
  principal     = "sns.amazonaws.com"
  source_arn    = aws_sns_topic.news_updates.arn
}

resource "aws_lambda_function" "news_processor_async" {
  function_name = "news_processor_async"
  role          = aws_iam_role.lambda_role.arn
  handler       = "lambda_function.lambda_handler"
  runtime       = "python3.9"
  timeout       = 120 # Increase from 30 to 120
  memory_size   = 128

  filename = "${path.module}/../news_processor_async.zip"

  environment {
    variables = {
      PROCESSOR_LAMBDA_NAME = aws_lambda_function.news_processor.function_name
    }
  }
}

# IAM policy for the async processor to invoke other Lambdas
resource "aws_iam_role_policy" "lambda_invoke_policy" {
  name = "lambda_invoke_policy"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "lambda:InvokeFunction"
        ]
        Resource = [
          "${aws_lambda_function.news_processor.arn}"
        ]
      }
    ]
  })
}

# API Gateway resource for async processor
resource "aws_api_gateway_resource" "process_async_resource" {
  rest_api_id = aws_api_gateway_rest_api.news_api.id
  parent_id   = aws_api_gateway_rest_api.news_api.root_resource_id
  path_part   = "process-async"
}

# API Gateway method for async processor
resource "aws_api_gateway_method" "process_async_method" {
  rest_api_id   = aws_api_gateway_rest_api.news_api.id
  resource_id   = aws_api_gateway_resource.process_async_resource.id
  http_method   = "POST"
  authorization = "NONE"
}

# API Gateway integration with async Lambda
resource "aws_api_gateway_integration" "process_async_integration" {
  rest_api_id = aws_api_gateway_rest_api.news_api.id
  resource_id = aws_api_gateway_resource.process_async_resource.id
  http_method = aws_api_gateway_method.process_async_method.http_method

  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.news_processor_async.invoke_arn
}

# Lambda permission for API Gateway
resource "aws_lambda_permission" "api_gateway_processor_async" {
  statement_id  = "AllowExecutionFromAPIGatewayAsync"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.news_processor_async.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.news_api.execution_arn}/*/${aws_api_gateway_method.process_async_method.http_method}${aws_api_gateway_resource.process_async_resource.path}"
}

# EventBridge rule to trigger news processor (7:10 AM JST / 10:10 PM UTC)
resource "aws_cloudwatch_event_rule" "daily_news_processing" {
  name                = "daily_news_processing"
  description         = "Triggers Lambda to process news daily at 7:10 AM Japan time (10 minutes after collection)"
  schedule_expression = "cron(10 22 * * ? *)"
}

# EventBridge target to Lambda for news processor
resource "aws_cloudwatch_event_target" "news_processor_target" {
  rule      = aws_cloudwatch_event_rule.daily_news_processing.name
  target_id = "news_processor"
  arn       = aws_lambda_function.news_processor.arn
}

# Lambda permission for EventBridge (for news processor)
resource "aws_lambda_permission" "allow_eventbridge_processor" {
  statement_id  = "AllowExecutionFromEventBridgeProcessor"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.news_processor.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_news_processing.arn
}
