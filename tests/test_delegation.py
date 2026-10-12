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

    def test_cron_inherits_live_parent_and_joins_without_registry_override(self):
        for model in ("fixture-luna", "fixture-other"):
            self.parent.model = model
            result = dispatch(self.ctx, {"goal": "Inspect assigned evidence"}, owned_cron=True)
            parent, routing, background, request = self.calls[-1]
            self.assertIs(parent, self.parent)
            self.assertEqual(parent.model, model)
            self.assertEqual(routing, {})
            self.assertFalse(background)
            self.assertIn("results", result)
        self.ctx.dispatch_tool.assert_not_called()

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

    def test_unsupported_native_version_refuses_instead_of_silent_model_change(self):
        self.modules["tools.delegate_tool"].delegate_task = lambda goal: "{}"
        with self.assertRaisesRegex(ValueError, "lacks per-call"):
            dispatch(self.ctx, {"goal": "x"}, owned_cron=True)
        self.ctx.dispatch_tool.assert_not_called()

    def test_compatible_cron_uses_public_route_and_pin_exceptions_are_explicit(self):
        self.ctx.dispatch_tool.return_value = json.dumps({'results':[{'status':'completed'}]})
        with patch('hermes_muse.delegation.settings', return_value={}):
            result = dispatch(self.ctx, {'goal':'Inspect evidence'}, owned_cron=True)
        self.assertIn('public_native_route', result['muse_routing'])
        self.assertEqual([],self.calls)
        for cfg in ({'model':'different'}, {'provider':'different'}, {'base_url':'https://example.invalid'}, {'fallback_providers':[]}):
            with patch('hermes_muse.delegation.settings',return_value=cfg):
                result=dispatch(self.ctx, {'goal':'Inspect evidence'}, owned_cron=True)
            self.assertIn('legacy_parent_route_exception',result['muse_routing'])
            self.assertEqual({},self.calls[-1][1])

    def test_route_change_during_public_dispatch_is_unknown_not_retried(self):
        configs=[{}, {}, {'model':'changed'}]
        with patch('hermes_muse.delegation.settings', side_effect=configs):
            with self.assertRaisesRegex(ValueError,'changed during dispatch') as caught:
                dispatch(self.ctx, {'goal':'Inspect evidence'}, owned_cron=True)
        self.assertEqual('dispatched',caught.exception.native_result['status'])
        self.assertEqual(1,self.ctx.dispatch_tool.call_count)
        self.assertEqual([],self.calls)

    def test_model_toolsets_and_excess_batch_refused_before_provider(self):
        with patch('hermes_muse.delegation.settings',return_value={'max_concurrent_children':1}):
            for req in ({'tasks':[{'goal':'One','toolsets':['terminal']}]}, {'tasks':[{'goal':'One'},{'goal':'Two'}]}):
                with self.assertRaises(ValueError):dispatch(self.ctx,req,owned_cron=True)
        self.assertEqual([],self.calls);self.ctx.dispatch_tool.assert_not_called()
