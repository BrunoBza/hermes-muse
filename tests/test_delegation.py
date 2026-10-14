import json
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from hermes_muse.delegation import dispatch


class DelegationTests(unittest.TestCase):
    def setUp(self):
        self.parent = SimpleNamespace(valid_tool_names={"delegate_task"}, model="fixture-luna")
        self.ctx = SimpleNamespace(dispatch_tool=Mock(return_value=json.dumps({"status": "dispatched"})))
        self.calls = []
        lifecycle = types.ModuleType("agent.subagent_lifecycle")
        lifecycle.get_active_subagent_parent = lambda: self.parent
        native = types.ModuleType("tools.delegate_tool")
        def delegate_task(*, parent_agent, credentials_cfg=None, background=True, **request):
            self.calls.append((parent_agent, credentials_cfg, background, request))
            return json.dumps({"results": [{"status": "completed"}]})
        native.delegate_task = delegate_task
        self.modules = {"agent.subagent_lifecycle": lifecycle, "tools.delegate_tool": native}
        patcher = patch.dict(sys.modules, self.modules)
        patcher.start()
        self.addCleanup(patcher.stop)
        route = patch("hermes_muse.delegation.settings", return_value=None)
        route.start(); self.addCleanup(route.stop)

    def test_cron_uses_public_dispatch_with_live_parent(self):
        request = {"goal":"Inspect assigned evidence"}
        dispatch(self.ctx, request, owned_cron=True)
        self.ctx.dispatch_tool.assert_called_once_with("delegate_task",request,parent_agent=self.parent)
        self.assertEqual(self.calls, [])

    def test_ordinary_conversation_keeps_native_registry_routing(self):
        request = {"goal": "Read the sources"}
        dispatch(self.ctx, request)
        self.ctx.dispatch_tool.assert_called_once_with("delegate_task", request, parent_agent=self.parent)
        self.assertEqual(self.calls, [])

    def test_no_tool_access_no_spawn_and_model_cannot_supply_route(self):
        for request in ({"goal": "x", "credentials_cfg": {}}, {"goal": "x", "owned_cron": True},
                        {"tasks": [{"goal": "x", "acp_command": "arbitrary"}]}, {"tasks": ["x"]}):
            with self.assertRaises(ValueError):
                dispatch(self.ctx, request, owned_cron=True)
        self.parent.valid_tool_names = set()
        with self.assertRaisesRegex(ValueError, "enabled"):
            dispatch(self.ctx, {"goal": "x"}, owned_cron=True)
        self.assertEqual(self.calls, [])

    def test_configured_routes_never_use_private_credentials_bypass(self):
        for cfg in ({}, {'model':'different'}, {'provider':'different'}, {'reasoning_effort':'high'}, None):
            self.ctx.dispatch_tool.reset_mock()
            with patch('hermes_muse.delegation.settings', return_value=cfg):
                dispatch(self.ctx, {'goal':'Inspect evidence'}, owned_cron=True)
            self.ctx.dispatch_tool.assert_called_once_with('delegate_task', {'goal':'Inspect evidence'}, parent_agent=self.parent)
        self.assertEqual(self.calls, [])

    def test_native_failure_is_returned_without_retry(self):
        self.ctx.dispatch_tool.return_value = json.dumps({'error':'quota unavailable'})
        with self.assertRaises(ValueError) as caught:
            dispatch(self.ctx, {'goal':'Inspect evidence'}, owned_cron=True)
        self.assertEqual(caught.exception.native_result, {'error':'quota unavailable'})
        self.assertEqual(self.ctx.dispatch_tool.call_count, 1)

    def test_model_toolsets_and_excess_batch_refused_before_provider(self):
        with patch('hermes_muse.delegation.settings',return_value={'max_concurrent_children':1}):
            for req in ({'tasks':[{'goal':'One','toolsets':['terminal']}]}, {'tasks':[{'goal':'One'},{'goal':'Two'}]}):
                with self.assertRaises(ValueError):dispatch(self.ctx,req,owned_cron=True)
        self.assertEqual([],self.calls);self.ctx.dispatch_tool.assert_not_called()
