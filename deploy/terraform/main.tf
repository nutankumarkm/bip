terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "BIP"
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  }
}

# -----------------------------------------------------------------------------
# Networking: VPC & Subnets
# -----------------------------------------------------------------------------

data "aws_availability_zones" "available" {
  state = "available"
}

resource "aws_vpc" "bip_vpc" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name = "bip-vpc-${var.environment}"
  }
}

resource "aws_internet_gateway" "gw" {
  vpc_id = aws_vpc.bip_vpc.id

  tags = {
    Name = "bip-igw-${var.environment}"
  }
}

resource "aws_subnet" "public_1" {
  vpc_id            = aws_vpc.bip_vpc.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 4, 0)
  availability_zone = data.aws_availability_zones.available.names[0]
  map_public_ip_on_launch = true

  tags = {
    Name = "bip-public-subnet-1"
  }
}

resource "aws_subnet" "public_2" {
  vpc_id            = aws_vpc.bip_vpc.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 4, 1)
  availability_zone = data.aws_availability_zones.available.names[1]
  map_public_ip_on_launch = true

  tags = {
    Name = "bip-public-subnet-2"
  }
}

resource "aws_subnet" "private_1" {
  vpc_id            = aws_vpc.bip_vpc.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 4, 2)
  availability_zone = data.aws_availability_zones.available.names[0]

  tags = {
    Name = "bip-private-subnet-1"
  }
}

resource "aws_subnet" "private_2" {
  vpc_id            = aws_vpc.bip_vpc.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 4, 3)
  availability_zone = data.aws_availability_zones.available.names[1]

  tags = {
    Name = "bip-private-subnet-2"
  }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.bip_vpc.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.gw.id
  }

  tags = {
    Name = "bip-public-rt"
  }
}

resource "aws_route_table_association" "pub_1" {
  subnet_id      = aws_subnet.public_1.id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "pub_2" {
  subnet_id      = aws_subnet.public_2.id
  route_table_id = aws_route_table.public.id
}

# -----------------------------------------------------------------------------
# Security Groups
# -----------------------------------------------------------------------------

resource "aws_security_group" "alb" {
  name        = "bip-alb-sg-${var.environment}"
  description = "Public HTTP/HTTPS traffic to ALB"
  vpc_id      = aws_vpc.bip_vpc.id

  ingress {
    description = "HTTP ingress"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS ingress"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "ecs_tasks" {
  name        = "bip-ecs-tasks-sg-${var.environment}"
  description = "Traffic from ALB to ECS Fargate tasks"
  vpc_id      = aws_vpc.bip_vpc.id

  ingress {
    description     = "Traffic from ALB"
    from_port       = 8000
    to_port         = 8001
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "db" {
  name        = "bip-rds-sg-${var.environment}"
  description = "Access to RDS Aurora PostgreSQL from ECS tasks"
  vpc_id      = aws_vpc.bip_vpc.id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs_tasks.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# -----------------------------------------------------------------------------
# Storage: S3 Raw Inbox with Lifecycle Purge
# -----------------------------------------------------------------------------

resource "aws_s3_bucket" "raw_inbox" {
  bucket = "bip-raw-inbox-${var.environment}-${var.aws_region}"

  tags = {
    Name = "bip-raw-inbox"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "raw_inbox_lifecycle" {
  bucket = aws_s3_bucket.raw_inbox.id

  rule {
    id     = "retention_purge"
    status = "Enabled"

    expiration {
      days = var.retention_days
    }
  }
}

# -----------------------------------------------------------------------------
# Database: RDS Aurora PostgreSQL
# -----------------------------------------------------------------------------

resource "aws_db_subnet_group" "bip_db_subnets" {
  name       = "bip-db-subnet-group-${var.environment}"
  subnet_ids = [aws_subnet.private_1.id, aws_subnet.private_2.id]
}

resource "aws_rds_cluster" "aurora" {
  cluster_identifier      = "bip-aurora-cluster-${var.environment}"
  engine                  = "aurora-postgresql"
  engine_version          = "16.1"
  database_name           = var.db_name
  master_username         = var.db_username
  master_password         = var.db_password
  db_subnet_group_name    = aws_db_subnet_group.bip_db_subnets.name
  vpc_security_group_ids  = [aws_security_group.db.id]
  storage_encrypted       = true
  deletion_protection     = var.environment == "prod"
  backup_retention_period = 30
}

resource "aws_rds_cluster_instance" "aurora_instances" {
  count              = 2
  identifier         = "bip-aurora-instance-${var.environment}-${count.index}"
  cluster_identifier = aws_rds_cluster.aurora.id
  instance_class     = var.db_instance_class
  engine             = aws_rds_cluster.aurora.engine
  engine_version     = aws_rds_cluster.aurora.engine_version
}

# -----------------------------------------------------------------------------
# Application Load Balancer
# -----------------------------------------------------------------------------

resource "aws_lb" "main" {
  name               = "bip-alb-${var.environment}"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = [aws_subnet.public_1.id, aws_subnet.public_2.id]
}

resource "aws_lb_target_group" "api" {
  name        = "bip-api-tg-${var.environment}"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = aws_vpc.bip_vpc.id
  target_type = "ip"

  health_check {
    path                = "/health"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 5
    interval            = 15
  }
}

resource "aws_lb_target_group" "edge" {
  name        = "bip-edge-tg-${var.environment}"
  port        = 8001
  protocol    = "HTTP"
  vpc_id      = aws_vpc.bip_vpc.id
  target_type = "ip"

  health_check {
    path                = "/health"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 5
    interval            = 15
  }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}

# Path-based routing for Edge (/iclock/* and /gw/*)
resource "aws_lb_listener_rule" "edge_routing" {
  listener_arn = aws_lb.listener_rule_target if false else aws_lb_listener.http.arn
  priority     = 10

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.edge.arn
  }

  condition {
    path_pattern {
      values = ["/iclock/*", "/gw/*"]
    }
  }
}

# -----------------------------------------------------------------------------
# ECS Fargate Cluster & Service Definitions
# -----------------------------------------------------------------------------

resource "aws_ecs_cluster" "main" {
  name = "bip-cluster-${var.environment}"
}

resource "aws_iam_role" "ecs_execution_role" {
  name = "bip-ecs-execution-role-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_execution_attach" {
  role       = aws_iam_role.ecs_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_cloudwatch_log_group" "bip_logs" {
  name              = "/ecs/bip-${var.environment}"
  retention_in_days = 90
}
