"""UI write-route → CLI command. OSS UI actions must stay doable from the CLI."""

from __future__ import annotations

# Hosted-app shims that 404 or no-op in OSS. Not product writes.
HOSTED_SHIMS: frozenset[tuple[str, str]] = frozenset(
    {
        ("POST", "/api/auth/signout"),
        ("POST", "/api/evals/baseline"),
        ("POST", "/api/evals/promote-draft"),
        ("POST", "/api/evals/suggest-skill-updates"),
    }
)

# Every OSS write route maps to a CLI command (argv after `skillgate`).
# In-flight HTTP skip/kill map to foreground `check` (Ctrl+C stops a CLI run).
WRITE_ROUTE_CLI: dict[tuple[str, str], str] = {
    ("PUT", "/api/settings/keys/{name}"): "keys set",
    ("DELETE", "/api/settings/keys/{name}"): "keys clear",
    ("PUT", "/api/settings/judge"): "judge provider set",
    ("POST", "/api/judge/ping"): "judge provider test",
    ("POST", "/api/skills/import"): "import",
    ("POST", "/api/skills/pack-file"): "skill write",
    ("POST", "/api/skills/pack-upload"): "skill write",
    ("POST", "/api/skills/paste"): "skill paste",
    ("POST", "/api/skills/upload"): "import",
    ("POST", "/api/skills/apply-fix"): "skill write",
    ("POST", "/api/evals/generate"): "skill write",
    ("POST", "/api/evals/pin"): "case add",
    ("POST", "/api/evals/import-dataset"): "case import",
    ("POST", "/api/evals/fixture-bind"): "case bind",
    ("POST", "/api/runs"): "check",
    ("POST", "/api/runs/{run_id}/skip"): "check",
    ("POST", "/api/runs/{run_id}/kill"): "check",
    ("POST", "/api/deploy"): "deploy",
    ("POST", "/api/login/{agent}"): "login",
    ("POST", "/api/compare/models"): "compare models",
    ("POST", "/api/compare/versions"): "compare versions",
    ("POST", "/api/compare/{compare_id}/cancel"): "compare cancel",
}

READ_ROUTE_CLI: dict[tuple[str, str], str] = {
    ("GET", "/api/history"): "history",
    ("GET", "/api/runs/{run_id}"): "history show",
    ("GET", "/api/compare"): "compare list",
    ("GET", "/api/compare/{compare_id}"): "compare show",
    ("GET", "/api/evals/dataset"): "case list",
    ("GET", "/api/skills"): "list",
    ("GET", "/api/settings/keys"): "keys list",
    ("GET", "/api/settings/judge"): "judge provider show",
    ("GET", "/api/login/status"): "login --status",
    ("GET", "/api/checks"): "checks show",
    ("GET", "/api/checks/preview"): "checks show",
    ("GET", "/api/checks/{check_id}"): "checks show",
}
