provider aws {
  version = "2.68"
}

provider okta {
  version   = "3.3.0"
  org_name  = var.okta_org_name
  api_token = var.okta_api_token
}
