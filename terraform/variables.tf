variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "ap-southeast-2"
}

variable "app_name" {
  description = "Application name, used for resource naming and tagging"
  type        = string
  default     = "meat-ensemble"
}

variable "instance_type" {
  description = "EC2 instance type. t4g.nano (~$3/mo) for very low traffic, t4g.micro (~$6/mo) recommended."
  type        = string
  default     = "t4g.micro"
}

variable "root_volume_size_gb" {
  description = "Root EBS volume size in GB (holds app code and SQLite DB)"
  type        = number
  default     = 20
}

variable "domain_name" {
  description = "Primary domain (e.g. steakclub.example.com or example.com)"
  type        = string
}

variable "www_record" {
  description = "Also create a www.domain_name Route53 record"
  type        = bool
  default     = true
}

variable "route53_zone_id" {
  description = "Route53 hosted zone ID for the domain"
  type        = string
}

variable "key_name" {
  description = "EC2 key pair name for SSH. Leave null to use SSM Session Manager only (recommended)."
  type        = string
  default     = null
}

variable "ssh_allowed_cidrs" {
  description = "CIDRs allowed to SSH. Only used when key_name is set. Restrict to your IP (e.g. [\"1.2.3.4/32\"])."
  type        = list(string)
  default     = []
}

variable "repo_url" {
  description = "Git repository URL to clone (e.g. https://github.com/you/mutual_mastication.git)"
  type        = string
}

variable "secret_key" {
  description = "Flask SECRET_KEY. Use a long random string: python3 -c \"import secrets; print(secrets.token_hex(32))\""
  type        = string
  sensitive   = true
}

variable "certbot_email" {
  description = "Email for Let's Encrypt registration and expiry notices"
  type        = string
}
