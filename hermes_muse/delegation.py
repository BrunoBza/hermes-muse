"""Public native delegation respecting host routing and reasoning; execution stays native."""
import json
import os


def settings():
    try:
        from hermes_cli.config import load_config_readonly
        cfg = load_config_readonly().get("delegation") or {}
        return cfg if isinstance(cfg, dict) else None
    except Exception:
        return None  # Unknown configuration cannot prove public parent-route parity.


def concurrency_limit():
    cfg = settings()
    if cfg is None:
        return 1  # Unknown effective budget: preserve all work, allocate conservatively.
    raw = cfg.get("max_concurrent_children")
    if raw is None:
        raw = os.environ.get("DELEGATION_MAX_CONCURRENT_CHILDREN", 10)
    try:
        return min(3, max(1, int(raw)))
    except (ValueError, TypeError):
        return 3  # Native invalid-value fallback is 10; plugin ceiling stays three.


def validate(data, *, owned_cron=False):
    from agent.subagent_lifecycle import get_active_subagent_parent
    parent = get_active_subagent_parent()
    if parent is None or "delegate_task" not in getattr(parent, "valid_tool_names", ()):
        raise ValueError("Delegation requires an active parent with native delegate_task enabled")
    # Do not expose trusted native routing/transport kwargs through the state tool.
    allowed = {"goal", "context", "tasks", "output_schema", "images", "action", "subagent_id", "message"}
    if set(data) - allowed:
        raise ValueError("Unsupported delegation fields; model routing is selected by the host context")
    request = dict(data)
    if "tasks" in request:
        tasks = request["tasks"]
        if not isinstance(tasks, list) or any(not isinstance(task, dict) for task in tasks):
            raise ValueError("tasks must be a list of task objects")
        if any(set(task) - {"goal", "context", "output_schema", "images", "role"} for task in tasks):
            raise ValueError("Unsupported task fields; transport settings cannot be supplied by the model")
        if len(tasks) > concurrency_limit():
            raise ValueError("Batch exceeds effective Muse/user concurrency limit; split unstarted tasks before dispatch")
    return parent, request


def dispatch(ctx, data, *, owned_cron=False):
    parent, request = validate(data, owned_cron=owned_cron)
    raw = ctx.dispatch_tool("delegate_task", request, parent_agent=parent)
    result = json.loads(raw)
    if not isinstance(result, dict) or result.get("error") or result.get("ok") is False:
        error = ValueError("Native delegation returned an error; inspect its outcome before retrying")
        error.native_result = result
        raise error
    return result
