from global_influx import global_state
from utils.logger_utils import logger
import importlib.util
import os
import sys
import types

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
generated_proto_root = os.path.join(project_root, ".generated/external/serializers/proto")

sys.path.insert(0, project_root)
sys.path.insert(0, generated_proto_root)


def _register_generated_proto_package(package_name: str):
    package_path = os.path.join(generated_proto_root, package_name)
    if not os.path.isdir(package_path):
        return

    module = types.ModuleType(package_name)
    module.__path__ = [package_path]
    module.__package__ = package_name
    module.__file__ = os.path.join(package_path, "__init__.py")
    module.__spec__ = importlib.util.spec_from_loader(package_name, loader=None, is_package=True)
    if module.__spec__ is not None:
        module.__spec__.submodule_search_locations = [package_path]

    sys.modules[package_name] = module


def _load_generated_proto_module(package_name: str, module_name: str):
    package_path = os.path.join(generated_proto_root, package_name)
    module_path = os.path.join(package_path, f"{module_name}.py")
    if not os.path.isfile(module_path):
        return

    full_name = f"{package_name}.{module_name}"
    if full_name in sys.modules:
        return

    spec = importlib.util.spec_from_file_location(full_name, module_path)
    if spec is None or spec.loader is None:
        return

    module = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = module
    spec.loader.exec_module(module)
    setattr(sys.modules[package_name], module_name, module)


for package_name in [
    "actions",
    "app",
    "can",
    "configs",
    "data",
    "handcart",
    "influxlogger",
    "lapcounter",
    "mongodb",
    "sessions",
    "telemetry",
    "tpms",
]:
    _register_generated_proto_package(package_name)
    package_path = os.path.join(generated_proto_root, package_name)
    if os.path.isdir(package_path):
        for file_name in os.listdir(package_path):
            if file_name.endswith(".py") and file_name != "__init__.py":
                _load_generated_proto_module(package_name, file_name[:-3])
