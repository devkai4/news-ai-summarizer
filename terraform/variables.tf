variable "aws_region" {
  description = "The AWS region to deploy resources"
  type        = string
  default     = "ap-northeast-1"
}

variable "bedrock_model_id" {
  description = "The AWS Bedrock model ID to use for processing"
  type        = string
  default     = "anthropic.claude-3-5-sonnet-20241022-v2:0"
}

variable "storage_type" {
  description = "The type of storage to use (s3 or dynamodb)"
  type        = string
  default     = "dynamodb"
}

variable "slack_webhook_url" {
  description = "Slack webhook URL for sending notifications"
  type        = string
}

variable "deploy_sns_to_slack" {
  description = "Whether to deploy the SNS-to-Slack Lambda function"
  type        = bool
  default     = false
}

variable "schedule_expression" {
  description = "CloudWatch Events schedule expression"
  type        = string
  default     = "cron(0 0 * * ? *)" # Daily at midnight UTC
}

variable "access_key" {
  description = "AWS アクセスキー"
  type        = string
  sensitive   = true
}

variable "secret_key" {
  description = "AWS シークレットキー"
  type        = string
  sensitive   = true
}
