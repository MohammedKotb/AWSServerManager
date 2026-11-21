terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = "eu-central-1" # يمكنك تغييره لمنطقتك
}

# 1. إنشاء الدور الأمني للصلاحيات
resource "aws_iam_role" "ec2_control_role" {
  name = "EC2ControlRole"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })
}

# 2. ربط السياسات المطلوبة بالدور
resource "aws_iam_role_policy" "ec2_policies" {
  name = "EC2ControlPolicies"
  role = aws_iam_role.ec2_control_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ec2:DescribeInstances",
          "ec2:StartInstances",
          "ec2:StopInstances",
          "ce:GetCostAndUsage"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_instance_profile" "ec2_profile" {
  name = "EC2ControlInstanceProfile"
  role = aws_iam_role.ec2_control_role.name
}

# 3. مجموعة الأمان (Security Group)
resource "aws_security_group" "server_sg" {
  name        = "ec2-control-sg"
  description = "Security group for controlled EC2 server"

  ingress {
    from_port   = 3389
    to_port     = 3389
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"] # يفضل تحديدها بـ IP الخاص بك للأمان
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# 4. تشغيل سيرفر الـ EC2
resource "aws_instance" "windows_server" {
  ami                  = "ami-0c760b2d305cf171a" # تأكد من تحديثها لمعرف AMI ويندوز في منطقتك
  instance_type        = "t3.medium"
  iam_instance_profile = aws_iam_instance_profile.ec2_profile.name
  vpc_security_group_ids = [aws_security_group.server_sg.id]

  metadata_options {
    http_put_response_hop_limit = 1
  }

  tags = {
    Name = "MyDevServer"
  }
}

output "instance_id" {
  value = aws_instance.windows_server.id
}