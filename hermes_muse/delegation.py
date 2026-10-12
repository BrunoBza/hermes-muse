"""Per-call model inheritance for Muse-owned Cron work; execution stays native."""
import inspect
import copy
import json
import os


def settings():
    try:
        from hermes_cli.config import load_config_readonly
        if os.environ.get("HERMES_IGNORE_USER_CONFIG") == "1":
            return None  # Native legacy config owner differs; do not infer route parity.
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


def _compatible(cfg):
    if cfg is None:
        return False
    return not any(cfg.get(k) not in (None, "", {}, []) if k != "fallback_providers" else cfg.get(k) is not None
                   for k in ("model", "provider", "base_url", "api_key", "api_mode", "command", "args", "request_overrides", "fallback_providers"))


def parent_route_compatible():
    return _compatible(settings())

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
    if owned_cron and not parent_route_compatible():
        from tools.delegate_tool import delegate_task
        if "credentials_cfg" not in inspect.signature(delegate_task).parameters:
            raise ValueError("This Hermes build lacks per-call delegation routing; review directly or update Hermes")
    return parent, request


def dispatch(ctx, data, *, owned_cron=False):
    parent, request = validate(data, owned_cron=owned_cron)
    route_before = copy.deepcopy(settings()) if owned_cron else None
    legacy_route = owned_cron and not _compatible(route_before)
    if legacy_route:
        from tools.delegate_tool import delegate_task
        # Empty routing inherits the live parent's model, endpoint and fallback route.
        # Native concurrency, permissions, reasoning and iteration settings still apply.
        raw = delegate_task(**request, parent_agent=parent, credentials_cfg={}, background=False)
    else:
        raw = ctx.dispatch_tool("delegate_task", request, parent_agent=parent)
    result = json.loads(raw)
    if not isinstance(result, dict) or result.get("error") or result.get("ok") is False:
        error = ValueError("Native delegation returned an error; inspect its outcome before retrying")
        error.native_result = result
        raise error
    if owned_cron and not legacy_route and settings() != route_before:
        error = ValueError("Delegation routing changed during dispatch; inspect returned native owner, never relaunch unknown work")
        error.native_result = result
        raise error
    if owned_cron:
        result["muse_routing"] = ("legacy_parent_route_exception: configured/unknown delegation route conflicts; public scoped inherit-parent API unresolved"
                                  if legacy_route else "public_native_route: compatible unpinned configuration; native Cron owns synchronous fallback")
    return result
