"""Path traversal errors (shared to avoid import cycles)."""


class PathTraversalError(ValueError):
    """Resolved path escapes the allowed root."""
