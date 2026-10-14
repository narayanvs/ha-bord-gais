"""Load pure client modules without importing Home Assistant."""
import importlib
from pathlib import Path
import sys
import types
name = 'bge_test_component'
package = types.ModuleType(name)
package.__path__ = [str(Path(__file__).resolve().parents[1] / 'custom_components' / 'bord_gais_energy')]
sys.modules.setdefault(name, package)
client = importlib.import_module(name + '.client')
model = importlib.import_module(name + '.account_data')
