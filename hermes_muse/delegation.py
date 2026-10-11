"""Per-call model inheritance for Muse-owned Cron work; execution stays native."""
import inspect
import json


def dispatch(ctx, data, *, owned_cron=False):
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
        if any(set(task) - {"goal", "context", "toolsets", "output_schema", "images", "role"} for task in tasks):
            raise ValueError("Unsupported task fields; transport settings cannot be supplied by the model")
    if owned_cron:
        from tools.delegate_tool import delegate_task
        if "credentials_cfg" not in inspect.signature(delegate_task).parameters:
            raise ValueError("This Hermes build lacks per-call delegation routing; review directly or update Hermes")
        # Empty routing inherits the live parent's model, endpoint and fallback route.
        # Native concurrency, permissions, reasoning and iteration settings still apply.
        raw = delegate_task(**request, parent_agent=parent, credentials_cfg={}, background=False)
    else:
        raw = ctx.dispatch_tool("delegate_task", request, parent_agent=parent)
    return json.loads(raw)
