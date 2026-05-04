output "public_ip" {
  description = "Elastic IP — point your domain here if not using Route53"
  value       = aws_eip.app.public_ip
}

output "instance_id" {
  description = "EC2 instance ID"
  value       = aws_instance.app.id
}

output "app_url" {
  description = "Application URL"
  value       = "https://${var.domain_name}"
}

output "ssm_connect" {
  description = "Connect to the instance via SSM (no SSH key needed)"
  value       = "aws ssm start-session --target ${aws_instance.app.id} --region ${var.aws_region}"
}

output "ssh_connect" {
  description = "SSH command (only if key_name was set)"
  value       = var.key_name != null ? "ssh -i ~/.ssh/${var.key_name}.pem ec2-user@${aws_eip.app.public_ip}" : "SSH disabled — use SSM"
}

output "bootstrap_log" {
  description = "Watch the bootstrap log on the instance"
  value       = "sudo tail -f /var/log/user_data.log"
}
