# ── SES domain verification ──────────────────────────────────────────────────
# NOTE: SES starts in sandbox mode. To send to unverified addresses you must
# request production access in the AWS console (SES → Account dashboard).
resource "aws_ses_domain_identity" "app" {
  domain = var.domain_name
}

resource "aws_ses_domain_dkim" "app" {
  domain = aws_ses_domain_identity.app.domain
}

# Domain ownership TXT record
resource "aws_route53_record" "ses_verification" {
  zone_id = var.route53_zone_id
  name    = "_amazonses.${var.domain_name}"
  type    = "TXT"
  ttl     = 600
  records = [aws_ses_domain_identity.app.verification_token]
}

# Three DKIM CNAME records
resource "aws_route53_record" "ses_dkim" {
  count   = 3
  zone_id = var.route53_zone_id
  name    = "${aws_ses_domain_dkim.app.dkim_tokens[count.index]}._domainkey.${var.domain_name}"
  type    = "CNAME"
  ttl     = 600
  records = ["${aws_ses_domain_dkim.app.dkim_tokens[count.index]}.dkim.amazonses.com"]
}

# Allow the EC2 instance role to send email via SES
resource "aws_iam_role_policy" "ses_send" {
  name = "${var.app_name}-ses-send"
  role = aws_iam_role.app.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["ses:SendEmail", "ses:SendRawEmail"]
      Resource = ["arn:aws:ses:${var.aws_region}:*:identity/${var.domain_name}"]
    }]
  })
}

output "ses_verify_cmd" {
  description = "Check SES domain verification status"
  value       = "aws ses get-identity-verification-attributes --identities ${var.domain_name} --region ${var.aws_region}"
}
