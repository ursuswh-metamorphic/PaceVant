class OpsError(RuntimeError):
    """Messages contain names/reasons only, never secret values or RPC credentials."""
