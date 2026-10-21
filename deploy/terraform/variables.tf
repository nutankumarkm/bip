variable "aws_region" {
  description = "AWS region for BIP infrastructure deployment"
  type        = string
  default     = "ap-south-1"
}

variable "environment" {
  description = "Deployment environment (e.g. prod, staging, dev)"
  type        = string
  default     = "prod"
}

variable "vpc_cidr" {
  description = "CIDR block for the BIP VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "db_name" {
  description = "PostgreSQL database name"
  type        = string
  default     = "bip_prod"
}

variable "db_username" {
  description = "Master database username"
  type        = string
  default     = "bip_admin"
}

variable "db_password" {
  description = "Master database password"
  type        = string
  sensitive   = true
}

variable "db_instance_class" {
  description = "RDS Aurora instance type"
  type        = string
  default     = "db.r6g.large"
}

variable "app_image" {
  description = "ECR container image URL for BIP API and Edge services"
  type        = string
  default     = "123456789012.dkr.ecr.ap-south-1.amazonaws.com/bip:latest"
}

variable "api_cpu" {
  description = "Fargate CPU units for API task"
  type        = number
  default     = 1024
}

variable "api_memory" {
  description = "Fargate Memory (MB) for API task"
  type        = number
  default     = 2048
}

variable "edge_cpu" {
  description = "Fargate CPU units for Edge task"
  type        = number
  default     = 1024
}

variable "edge_memory" {
  description = "Fargate Memory (MB) for Edge task"
  type        = number
  default     = 2048
}

variable "retention_days" {
  description = "Default raw biometric punch retention period in days"
  type        = number
  default     = 730
}
