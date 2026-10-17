export function agentSessionLabel(row: {
  auth?: string
  status?: string
}): "signed in" | "not signed in" {
  if (row.auth === "cli_login" || row.auth === "api_key") {
    return "signed in"
  }
  if (row.status === "logged in" || row.status === "API key") {
    return "signed in"
  }
  return "not signed in"
}
