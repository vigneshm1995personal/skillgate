from __future__ import annotations

import re

from skillgate_ai.span_facts import _INVOKE_TOOLS

TOOL_CHECK_SCORERS = frozenset({"tool_calls", "consequential_calls"})

_INTERPRETERS = frozenset({"python", "python3", "node", "bash", "sh", "uv", "npx", "ruby", "perl"})
_SAFE_TOOLS = frozenset(
    {
        "read",
        "read_file",
        "write",
        "edit",
        "multi_edit",
        "search_replace",
        "apply_patch",
        "glob",
        "grep",
        "ls",
        "list_dir",
        "delete_file",
        "todo_write",
        "task",
        "web_fetch",
        "web_search",
        "codebase_search",
        "notebook_edit",
    }
)
_READ_VERBS = frozenset(
    {
        "get",
        "list",
        "retrieve",
        "read",
        "search",
        "show",
        "describe",
        "status",
        "fetch",
        "preview",
        "validate",
        "plan",
        "what_if",
        "dry_run",
        "what-if",
    }
)
_SHELL_TOOLS = frozenset(_INVOKE_TOOLS) | {"run"}
_SEP = re.compile(r"(?:&&|\|\||;|\||\$\(|\n)")
_SUDO_PREFIX = re.compile(r"^sudo\s+", re.IGNORECASE)
_ENV_PREFIX = re.compile(r"^(?:[A-Za-z_][A-Za-z0-9_]*=\S+\s+)+")

# Patterns are matched with re.match against the command stem (§3.2.4).
_SHELL_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("shell:git_push", re.compile(r"^git\b(?:\s+\S+)*\s+push\b", re.IGNORECASE)),
    ("shell:terraform_apply", re.compile(r"^terraform\s+(apply|destroy)\b", re.IGNORECASE)),
    (
        "shell:kubectl_mutate",
        re.compile(
            r"^kubectl\s+(apply|delete|create|scale|rollout\s+restart|patch)\b",
            re.IGNORECASE,
        ),
    ),
    ("shell:helm_mutate", re.compile(r"^helm\s+(install|upgrade|uninstall)\b", re.IGNORECASE)),
    ("shell:azd_up", re.compile(r"^azd\s+(up|deploy|provision|down)\b", re.IGNORECASE)),
    (
        "shell:az_mutate",
        re.compile(
            r"^az\b(?:\s+\S+)*\s+"
            r"(create|delete|deploy|up|update|swap|restart|start|stop|purge)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "shell:gcloud_mutate",
        re.compile(r"^gcloud\b(?:\s+\S+)*\s+(deploy|create|delete)\b", re.IGNORECASE),
    ),
    (
        "shell:aws_mutate",
        re.compile(
            r"^aws\b(?:\s+\S+)*\s+"
            r"(create-|delete-|put-|terminate-|update-|deploy)\S*",
            re.IGNORECASE,
        ),
    ),
    (
        "shell:platform_deploy",
        re.compile(
            r"^(?:vercel\s+(?:deploy|--prod)|netlify\s+deploy|fly\s+deploy|firebase\s+deploy)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "shell:package_publish",
        re.compile(
            r"^(?:npm\s+publish|twine\s+upload|cargo\s+publish|docker\s+push|"
            r"gh\s+release\s+create|gh\s+pr\s+merge)\b",
            re.IGNORECASE,
        ),
    ),
    ("shell:sendmail", re.compile(r"^(?:sendmail\b|mail\s+-s\b)", re.IGNORECASE)),
)
