"""Compile the repository's protobuf definitions to Python modules."""

import importlib
import sys
from pathlib import Path
from types import ModuleType

from grpc_tools import protoc

from src.utils.logger_utils import logger

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
PROTO_ROOT: Path = PROJECT_ROOT / "lib" / "external" / "serializers" / "proto"
GENERATED_ROOT: Path = PROJECT_ROOT / ".generated"


def compile_proto_files() -> Path:
    """Compile all checked-in ``.proto`` files into ``.generated``.

    Returns:
        The directory containing the generated Python modules.

    Raises:
        RuntimeError: If no proto definitions are found or compilation fails.
    """
    proto_files = sorted(PROTO_ROOT.rglob("*.proto"))
    if not proto_files:
        raise RuntimeError(f"No .proto files found in {PROTO_ROOT}")

    GENERATED_ROOT.mkdir(parents=True, exist_ok=True)
    args = [
        "protoc",
        f"-I{PROTO_ROOT}",
        f"--python_out={GENERATED_ROOT}",
        *(str(proto_file) for proto_file in proto_files),
    ]

    logger.info("Compiling %d protobuf definitions into %s", len(proto_files),
                GENERATED_ROOT)
    result = protoc.main(args)
    if result != 0:
        raise RuntimeError(
            f"Failed to compile protobuf definitions (protoc exit code {result})"
        )

    logger.info("Compiled %d protobuf definitions into %s", len(proto_files),
                GENERATED_ROOT)
    return GENERATED_ROOT


def import_generated_module(module_name: str) -> ModuleType:
    """Import a module generated under ``.generated``."""
    generated_root = str(GENERATED_ROOT)
    if generated_root not in sys.path:
        sys.path.insert(0, generated_root)
    return importlib.import_module(module_name)
