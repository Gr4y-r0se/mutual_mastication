# IAM role — grants SSM Session Manager access so you can shell in without SSH keys
resource "aws_iam_role" "app" {
  name = "${var.app_name}-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.app.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "app" {
  name = "${var.app_name}-profile"
  role = aws_iam_role.app.name
}

resource "aws_instance" "app" {
  ami                    = data.aws_ami.al2023_arm.id
  instance_type          = var.instance_type
  subnet_id              = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.app.id]
  key_name               = var.key_name
  iam_instance_profile   = aws_iam_instance_profile.app.name

  root_block_device {
    volume_type           = "gp3"
    volume_size           = var.root_volume_size_gb
    encrypted             = true
    delete_on_termination = true
  }

  user_data = templatefile("${path.module}/user_data.sh", {
    app_name         = var.app_name
    repo_url         = var.repo_url
    domain_name      = var.domain_name
    secret_key       = var.secret_key
    certbot_email    = var.certbot_email
    ses_from_address = var.ses_from_address
    ses_region       = var.aws_region
    # Pre-computed so user_data.sh doesn't need conditional logic
    certbot_domains = var.www_record ? "-d ${var.domain_name} -d www.${var.domain_name}" : "-d ${var.domain_name}"
    server_name     = var.www_record ? "${var.domain_name} www.${var.domain_name}" : var.domain_name
  })

  tags = { Name = var.app_name }
}

# Elastic IP — static public IP so your Route53 record never needs updating
resource "aws_eip" "app" {
  domain = "vpc"

  tags = { Name = "${var.app_name}-eip" }
}

resource "aws_eip_association" "app" {
  instance_id   = aws_instance.app.id
  allocation_id = aws_eip.app.id
}
