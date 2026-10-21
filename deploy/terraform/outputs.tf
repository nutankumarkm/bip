output "alb_dns_name" {
  description = "Public DNS name of the Application Load Balancer"
  value       = aws_lb.main.dns_name
}

output "api_url" {
  description = "Consumer API and Ops Console base URL"
  value       = "http://${aws_lb.main.dns_name}/v1"
}

output "edge_url" {
  description = "Device Edge push and Gateway base URL"
  value       = "http://${aws_lb.main.dns_name}/iclock"
}

output "rds_cluster_endpoint" {
  description = "Aurora PostgreSQL cluster writer endpoint"
  value       = aws_rds_cluster.aurora.endpoint
}

output "rds_cluster_reader_endpoint" {
  description = "Aurora PostgreSQL cluster reader endpoint"
  value       = aws_rds_cluster.aurora.reader_endpoint
}

output "s3_raw_inbox_bucket" {
  description = "Name of the S3 Raw Ingest bucket"
  value       = aws_s3_bucket.raw_inbox.bucket
}

output "ecs_cluster_name" {
  description = "Name of the ECS Fargate cluster"
  value       = aws_ecs_cluster.main.name
}
