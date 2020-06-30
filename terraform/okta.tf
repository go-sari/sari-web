variable okta_org_name {
  type        = string
  description = "The organization name in the company's Okta account. Defaults to var.organization value."
}

variable okta_api_token {
  type        = string
  description = "The token to access the Okta API."
}

variable saml_sso_base_url {
  type        = string
  description = "The SAML IdP Destination Base URL."
  default     = null
}

variable okta_group_name {
  type        = string
  description = "The Okta group that will have the SARI-Web application enabled."
}

variable idp_name {
  type    = string
  default = "Okta4SARI"
}

variable aws_accounts {
  type        = map(string)
  description = "The AWS accounts supported by SARI-Web."
}

data aws_region current {}

data aws_api_gateway_rest_api this {
  name = "sari-web"
}

locals {
  saml_sso_base_url = var.saml_sso_base_url != null ? var.saml_sso_base_url : "https://${data.aws_api_gateway_rest_api.this.id}.execute-api.${data.aws_region.current.name}.amazonaws.com/_"
  saml_sso_url = "${local.saml_sso_base_url}/saml/idp/sari"
}

resource okta_app_saml sari-console {
  label                    = "SARI"
  sso_url                  = local.saml_sso_url
  recipient                = "https://signin.aws.amazon.com/saml"
  destination              = local.saml_sso_url
  audience                 = "urn:amazon:webservices"
  assertion_signed         = true
  hide_ios                 = true
  key_years_valid          = 10
  subject_name_id_template = "$${user.userName}"
  subject_name_id_format   = "urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified"
  response_signed          = true
  signature_algorithm      = "RSA_SHA256"
  digest_algorithm         = "SHA256"
  honor_force_authn        = true
  authn_context_class_ref  = "urn:oasis:names:tc:SAML:2.0:ac:classes:PasswordProtectedTransport"
  user_name_template       = "$${source.email}"
  idp_issuer               = "http://www.okta.com/$${org.externalKey}"

  lifecycle {
    // See https://github.com/terraform-providers/terraform-provider-okta/issues/68
    ignore_changes = [groups]
  }

  attribute_statements {
    name      = "https://aws.amazon.com/SAML/Attributes/Role"
    namespace = "urn:oasis:names:tc:SAML:2.0:attrname-format:basic"
    values    = [for alias, acc in var.aws_accounts : "arn:aws:iam::${acc}:role/SARI,arn:aws:iam::${acc}:saml-provider/${var.idp_name}"]
  }

  attribute_statements {
    name      = "https://aws.amazon.com/SAML/Attributes/RoleSessionName"
    namespace = "urn:oasis:names:tc:SAML:2.0:attrname-format:basic"
    values    = ["user.email"]
  }

  attribute_statements {
    name      = "https://aws.amazon.com/SAML/Attributes/SessionDuration"
    namespace = "urn:oasis:names:tc:SAML:2.0:attrname-format:basic"
    values    = ["3600"]
  }

  attribute_statements {
    name      = "https://aws.amazon.com/SAML/Attributes/PrincipalTag:User"
    namespace = "urn:oasis:names:tc:SAML:2.0:attrname-format:basic"
    values    = ["user.email"]
  }

  attribute_statements {
    name      = "https://github.com/eliezio/sari/AccountAlias"
    namespace = "urn:oasis:names:tc:SAML:2.0:attrname-format:basic"
    values    = [for alias, acc in var.aws_accounts : "${acc},${alias}"]
  }
}

data okta_group this {
  name = var.okta_group_name
}

resource okta_app_group_assignment this {
  app_id   = okta_app_saml.sari-console.id
  group_id = data.okta_group.this.id
}
