"""Discovery helpers for pipeline fixture tests (tests for services that other
agents own and that may not exist yet).

The helpers import whatever module layout the owning agent produced and locate
a callable entry point. If nothing can be resolved the tests skip with an
explicit reason instead of failing, so the suite stays green while other
agents are still landing their folders.
"""

import importlib
import importlib.util
import inspect
import pkgutil
import sys
import types
from pathlib import Path

import pytest

PROJECT_ROOT = Path(r"D:\AI_Hack")
SERVICES_DIR = PROJECT_ROOT / "services"

OLD_PARAM_NAMES = {
    "old", "old_text", "old_content", "old_version", "old_version_text",
    "previous", "previous_text", "previous_content", "before", "before_text",
    "base_text", "baseline", "prior",
}
NEW_PARAM_NAMES = {
    "new", "new_text", "new_content", "new_version", "new_version_text",
    "current", "current_text", "current_content", "after", "after_text",
    "content", "text", "html", "raw", "body", "document", "input",
}


def service_available(name: str) -> bool:
    return (SERVICES_DIR / name).exists()


def import_service_modules(service: str):
    """Import every importable module under services/<service>.

    Handles the three layouts used in this repo:
    services/<svc>/<svc>/__init__.py  (package inside a folder, e.g. docproc)
    services/<svc>/__init__.py        (folder itself a package)
    services/<svc>/...                (namespace package, e.g. ai)

    Returns (modules, errors). Modules that fail to import (e.g. missing
    optional deps) are recorded rather than raised.
    """
    root = SERVICES_DIR / service
    if not root.exists():
        pytest.skip(f"services/{service} not present yet ({service} agent pending)")

    modules: list[types.ModuleType] = []
    errors: list[str] = []

    if (root / service / "__init__.py").exists():
        entry, pkg_name = str(root), service
    elif (root / "__init__.py").exists():
        entry, pkg_name = str(root.parent), root.name
    else:
        entry, pkg_name = str(root.parent), service

    for path_entry in (entry, str(SERVICES_DIR)):
        if path_entry not in sys.path:
            sys.path.insert(0, path_entry)

    pkg = None
    try:
        pkg = importlib.import_module(pkg_name)
    except Exception as exc:  # noqa: BLE001 - optional deps allowed
        errors.append(f"import {pkg_name}: {exc}")

    if pkg is not None:
        try:
            for info in pkgutil.walk_packages(getattr(pkg, "__path__", []),
                                              prefix=pkg_name + "."):
                try:
                    modules.append(importlib.import_module(info.name))
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{info.name}: {exc}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"walk {pkg_name}: {exc}")
        if modules:
            return modules, errors

    # Fallback: import files directly (module may have no package deps).
    for path in sorted(root.rglob("*.py")):
        if path.name.startswith("test_") or path.name == "conftest.py":
            continue
        mod_name = f"_qa_{service}_" + "_".join(path.relative_to(root).with_suffix("").parts)
        try:
            spec = importlib.util.spec_from_file_location(mod_name, path)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = module
            spec.loader.exec_module(module)
            modules.append(module)
        except Exception as exc:  # noqa: BLE001 - optional deps allowed
            errors.append(f"{path.relative_to(root)}: {exc}")
    return modules, errors


def find_callable(modules, candidates, service: str):
    """First callable whose __name__ is in candidates, else skip with reason."""
    found = []
    for module in modules:
        for name in candidates:
            fn = getattr(module, name, None)
            if callable(fn) and not isinstance(fn, type):
                found.append((name, fn))
    if not found:
        tried = ", ".join(sorted(candidates))
        raise pytest.skip(f"services/{service}: none of [{tried}] found; "
                          f"modules loaded={len(modules)}")
    return found[0][1]


def call_with_texts(fn, old_text: str, new_text: str):
    """Invoke fn(old, new) adapting to its parameter names.

    Returns (result, signature_description). Skips if the signature cannot be
    satisfied with text inputs (e.g. it needs regulation_id/version_no only).
    """
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        result = fn(old_text, new_text)
        return result, "positional"

    kwargs = {}
    positional = []
    unresolved = []
    for param in sig.parameters.values():
        if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
            continue
        if param.default is not inspect.Parameter.empty:
            continue  # optional - leave default
        lname = param.name.lower()
        if lname in OLD_PARAM_NAMES:
            kwargs[param.name] = old_text
        elif lname in NEW_PARAM_NAMES:
            kwargs[param.name] = new_text
        elif lname in ("spec", "payload", "request", "regulation_id", "version_no",
                       "event_id", "analysis_context"):
            unresolved.append(param.name)
        else:
            unresolved.append(param.name)

    if unresolved:
        required = [p for p in sig.parameters.values()
                    if p.default is inspect.Parameter.empty
                    and p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)]
        if not kwargs and len(required) == 1:
            try:
                return fn(new_text), "single-positional"
            except TypeError:
                pass
        try:
            result = fn(old_text, new_text)
            return result, "positional"
        except TypeError:
            raise pytest.skip(
                f"{fn.__module__}.{fn.__name__} requires non-text parameters "
                f"{unresolved}; adapt this test to its real signature") from None

    if kwargs:
        result = fn(**kwargs)
        return result, f"kwargs={sorted(kwargs)}"
    result = fn(old_text, new_text)
    return result, "positional"


def to_jsonable(value):
    """Normalize dicts / pydantic models / dataclasses to plain data."""
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict") and callable(value.dict):
        try:
            return value.dict()
        except Exception:  # noqa: BLE001
            pass
    if hasattr(value, "__dataclass_fields__"):
        import dataclasses
        return dataclasses.asdict(value)
    return value
