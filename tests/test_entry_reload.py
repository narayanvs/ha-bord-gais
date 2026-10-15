"""Exercise the entry listener without loading the complete HA runtime."""
import ast
from pathlib import Path
import types
import unittest
from unittest.mock import Mock

source = Path(__file__).resolve().parents[1] / 'custom_components/bord_gais_energy/__init__.py'
tree = ast.parse(source.read_text())
listener = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef)
                and node.name == 'async_update_options')
namespace = {'DEFAULT_POLL_HOURS': 168}
exec(compile(ast.Module(body=[listener], type_ignores=[]), str(source), 'exec'), namespace)


class Tests(unittest.IsolatedAsyncioTestCase):
    async def check(self, saved, live, options, expected):
        reload = Mock()
        hass = types.SimpleNamespace(config_entries=types.SimpleNamespace(async_schedule_reload=reload))
        entry = types.SimpleNamespace(entry_id='synthetic', data={'session': saved}, options=options,
            runtime_data=types.SimpleNamespace(poll_hours=168, client=types.SimpleNamespace(session=live)))
        await namespace['async_update_options'](hass, entry)
        if expected:
            reload.assert_called_once_with('synthetic')
        else:
            reload.assert_not_called()

    async def test_token_rotation_does_not_reload(self):
        await self.check({'refreshToken': 'rotated'}, {'refreshToken': 'rotated'}, {}, False)

    async def test_browser_reauth_schedules_reload(self):
        await self.check({'refreshToken': 'new-login'}, {'refreshToken': 'old-login'}, {}, True)

    async def test_polling_change_schedules_reload(self):
        await self.check({'refreshToken': 'same'}, {'refreshToken': 'same'}, {'poll_hours': 24}, True)
