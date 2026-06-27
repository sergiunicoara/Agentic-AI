"""
Live Red Team Worker.

This module runs ONLY inside its own subprocess, spawned by
sentinel.redteam.live_runner. Target code never executes in the main
Sentinel process — both discovery (inspecting the target's functions)
and invocation (calling a function with an adversarial payload) happen
here, in a fresh child process, after network sockets are patched and
(on POSIX) resource limits are applied.

Two modes, both print exactly one JSON line to stdout:

  --discover <module_file>
      Import the target module and report which top-level functions are
      safe to call with a raw adversarial string: first required
      parameter is str/bytes-annotated (or unannotated) and not named
      like a filesystem path. Prints a JSON list of [func_name, param_kind].

  <module_file> <func_name> <param_kind> <payload_file>
      Call module.func_name(payload) — payload read from payload_file,
      decoded as str or bytes per param_kind — and report the outcome.
"""
import importlib.util
import inspect
import io
import json
import sys
import uuid
from pathlib import Path

_PATHLIKE_NAMES = ("path", "dir", "file", "filename")


def _lock_down():
    """
    Apply containment before any target code is imported or called:
    - network sockets raise instead of connecting (no real egress)
    - (POSIX only) CPU-time and address-space limits
    There is no equivalent OS-level resource limit on Windows from pure
    Python stdlib; the per-call subprocess timeout in live_runner is the
    backstop there.
    """
    import socket

    def _blocked(*_args, **_kwargs):
        raise OSError("network access blocked by Sentinel red-team sandbox")

    # Block both DNS resolution and the connect step — covers urllib3/requests
    # (which resolve via getaddrinfo before connecting) and raw socket use.
    socket.socket.connect = _blocked
    socket.socket.connect_ex = _blocked
    socket.create_connection = _blocked
    socket.getaddrinfo = _blocked

    try:
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (2, 2))
        try:
            resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
        except (ValueError, OSError):
            pass  # platform doesn't support capping address space; CPU cap still applies
    except ImportError:
        pass  # Windows has no `resource` module


def _load_module(module_file: str):
    spec = importlib.util.spec_from_file_location(
        f"_sentinel_live_{uuid.uuid4().hex}", module_file
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _discover(module_file: str) -> list[tuple[str, str]]:
    module = _load_module(module_file)
    matches = []
    for name, fn in inspect.getmembers(module, inspect.isfunction):
        if fn.__module__ != module.__name__ or name.startswith("_"):
            continue
        try:
            sig = inspect.signature(fn)
        except (TypeError, ValueError):
            continue
        params = list(sig.parameters.values())
        if not params:
            continue
        first = params[0]
        if first.default is not inspect.Parameter.empty:
            continue  # only call functions whose first arg is required
        if any(p in first.name.lower() for p in _PATHLIKE_NAMES):
            continue  # never feed raw payloads into path-shaped parameters
        if first.annotation is str or first.annotation is inspect.Parameter.empty:
            matches.append((name, "str"))
        elif first.annotation is bytes:
            matches.append((name, "bytes"))
    return matches


def _invoke(module_file: str, func_name: str, param_kind: str, payload_file: str) -> dict:
    payload_text = Path(payload_file).read_text(encoding="utf-8")
    arg = payload_text.encode("utf-8") if param_kind == "bytes" else payload_text

    module = _load_module(module_file)
    fn = getattr(module, func_name)

    real_stdout = sys.stdout
    try:
        sys.stdout = io.StringIO()  # don't let target prints corrupt our JSON line
        result = fn(arg)
        return {"status": "completed", "return_repr": repr(result)[:200]}
    except Exception as e:
        return {
            "status": "raised_exception",
            "exception_type": type(e).__name__,
            "exception_msg": str(e)[:400],
            "network_blocked": "blocked by Sentinel red-team sandbox" in str(e),
        }
    finally:
        sys.stdout = real_stdout


def main():
    _lock_down()
    try:
        if sys.argv[1] == "--discover":
            print(json.dumps(_discover(sys.argv[2])))
        else:
            module_file, func_name, param_kind, payload_file = sys.argv[1:5]
            print(json.dumps(_invoke(module_file, func_name, param_kind, payload_file)))
    except Exception as e:
        print(json.dumps({"status": "worker_error", "error": str(e)[:300]}))


if __name__ == "__main__":
    main()
