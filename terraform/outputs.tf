output "api_invoke_url" {
  description = "The URL to invoke the API Gateway"
  value       = "${aws_api_gateway_deployment.news_api_deployment.invoke_url}"
}

output "news_bucket_name" {
  description = "The name of the S3 bucket for news storage"
  value       = aws_s3_bucket.news_bucket.bucket
}

output "news_table_name" {
  description = "The name of the DynamoDB table for news storage"
  value       = aws_dynamodb_table.news_table.name
}

output "news_collector_function_name" {
  description = "The name of the Lambda function for news collection"
  value       = aws_lambda_function.news_collector.function_name
}

output "news_processor_function_name" {
  description = "The name of the Lambda function for news processing"
  value       = aws_lambda_function.news_processor.function_name
}

output "sns_topic_arn" {
  description = "The ARN of the SNS topic for news updates"
  value       = aws_sns_topic.news_updates.arn
}