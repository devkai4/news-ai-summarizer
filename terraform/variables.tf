variable "aws_region" {
  description = "The AWS region to deploy resources"
  type        = string
  default     = "ap-northeast-1"
}

variable "bedrock_model_id" {
  description = "The AWS Bedrock model ID to use for processing"
  type        = string
  default     = "anthropic.claude-3-5-sonnet-20240620-v1:0"
}

variable "storage_type" {
  description = "The type of storage to use (s3 or dynamodb)"
  type        = string
  default     = "dynamodb"
}

variable "notification_email" {
  description = "Email address to send notifications to"
  type        = string
  default     = "devkai4@pm.me"
}

variable "schedule_expression" {
  description = "CloudWatch Events schedule expression"
  type        = string
  default     = "cron(0 0 * * ? *)" # Daily at midnight UTC
}
