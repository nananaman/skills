"""Unseen stdio transport checks using synthetic streams and mocked children.

No executable, server, history, private state, configuration or network is used.
Only fresh temporary synthetic source/progress files are written. These tests
cannot prove cross-process live idle or actual local-stdio availability.
"""

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch


WORKTREE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKTREE))
sys.path.insert(0, str(WORKTREE / "meta/skill-maintenance/scripts"))
import codex_proxy as P
import codex_reader as R

# Reuse the published schema fixture solely as protocol infrastructure; the
# byte streams, child behavior and stage cases below are new independent inputs.
spec = importlib.util.spec_from_file_location("published_stdio_schema", WORKTREE / "tests/test_reader_stdio.py")
schema_fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(schema_fixture)


class OwnedChild:
    def __init__(self, command, *, env, **options):
        self.command, self.env, self.options = command, env, options
        self.stdout, self.stdin = self.Output(self), self.Input(self)
        self.lines = queue.Queue()
        self.requests, self.pending, self.sent = [], b"", b""
        self.done = False
        self.silent_initialize = False
        self.invalid_initialize = False
        self.stubborn = False
        self.terminate_count = self.kill_count = self.wait_count = 0

    class Input:
        def __init__(self, child): self.child = child
        def write(self, data):
            child = self.child
            value = bytes(data)
            child.sent += value
            request = json.loads(value)
            if "id" not in request:
                return len(value)
            child.requests.append(request)
            if request["method"] == "initialize":
                if child.silent_initialize:
                    return len(value)
                result = {"userAgent": "codex_cli_rs/1.2.3 (Mac OS; arm64)",
                          "codexHome": child.env["CODEX_HOME"], "platformFamily": "unix", "platformOs": "macos"}
                if child.invalid_initialize:
                    result["platformFamily"] = False
            elif request["method"] == "thread/list":
                result = {"data": [], "nextCursor": None}
            else:
                raise AssertionError("metadata-only holdout attempted another history RPC")
            child.lines.put((json.dumps({"id": request["id"], "result": result}) + "\n").encode())
            return len(value)
        def close(self): pass

    class Output:
        def __init__(self, child): self.child = child
        def readline(self, limit):
            child = self.child
            if not child.pending:
                child.pending = child.lines.get(timeout=1)
            result, child.pending = child.pending[:limit], child.pending[limit:]
            return result
        def close(self):
            self.child.lines.put(b"")

    def poll(self): return 0 if self.done else None
    def terminate(self):
        self.terminate_count += 1
        if not self.stubborn:
            self.done = True
            self.lines.put(b"")
    def kill(self):
        self.kill_count += 1
        self.done = True
        self.lines.put(b"")
    def wait(self, timeout=None):
        self.wait_count += 1
        if self.stubborn and not self.done:
            raise subprocess.TimeoutExpired(self.command, timeout)
        return 0


class StdioUnseen(unittest.TestCase):
    def configuration(self, home):
        return {"codex_home": str(home), "codex_executable": "unseen-synthetic-codex",
                "transport": "local-stdio", "start_local_server": True,
                "acquisition_budget": P.AcquisitionBudget(4096, 1)}

    def bare_reader(self, data, max_bytes=128):
        reader = P.Proxy.__new__(P.Proxy)
        reader.transport = "local-stdio"
        reader.messages = queue.Queue()
        reader.budget = P.AcquisitionBudget(max_bytes, 1)
        source = io.BytesIO(data)
        reader.process = Mock(stdout=source)
        return reader, source

    def stage(self, temporary, stage, transport="local-stdio", startup=True):
        directory = Path(temporary)
        source = directory / "synthetic-source.json"
        if not source.exists():
            source.write_text(json.dumps({"version": 1, "source_id": "unseen-transport", "device_id": "synthetic",
                "host_id": "local", "path_flavour": "posix", "exclude_roots": [], "repos": [
                    {"id": "unseen/project", "cwd": str(Path.home() / "synthetic-unseen-cwd"),
                     "information_scope": "personal:unseen"}]}))
        args = ["reader", stage, "--transport", transport, "--codex-home", str(directory / "synthetic-home"),
                "--output", str(directory / (stage + ".json")), "--state", str(directory / "synthetic-state.json"),
                "--codex-executable", "unseen-synthetic-codex"]
        if startup:
            args.append("--start-local-server")
        if stage == "index":
            args.extend(["--source", str(source), "--since", "2024-01-01T00:00:00Z",
                         "--cutoff", "2024-01-02T00:00:00Z"])
        else:
            args.extend(["--selection", str(directory / "poison-selection.json")])
            if stage == "read": args.append("--read-completed")
        return args

    def test_local_turn_selection_rejected_before_input_or_spawn(self):
        with tempfile.TemporaryDirectory() as temporary:
            args = self.stage(temporary, "turns")
            with patch.object(sys, "argv", args), patch.object(R.sys, "platform", "darwin"), \
                 patch.object(Path, "read_text", side_effect=AssertionError("unapproved selection read")), \
                 patch.object(P, "inspect_cli") as inspect, patch.object(P.subprocess, "Popen") as spawn, \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(R.main(), 2)
                inspect.assert_not_called()
                spawn.assert_not_called()

    def test_local_body_stage_rejected_before_input_or_spawn(self):
        with tempfile.TemporaryDirectory() as temporary:
            args = self.stage(temporary, "read")
            with patch.object(sys, "argv", args), patch.object(R.sys, "platform", "darwin"), \
                 patch.object(Path, "read_text", side_effect=AssertionError("unapproved selection read")), \
                 patch.object(P, "inspect_cli") as inspect, patch.object(P.subprocess, "Popen") as spawn, \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(R.main(), 2)
                inspect.assert_not_called()
                spawn.assert_not_called()

    def test_local_index_is_allowed_and_owned_child_reaped(self):
        children = []
        def spawn(*args, **kwargs):
            child = OwnedChild(*args, **kwargs)
            children.append(child)
            return child
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(sys, "argv", self.stage(temporary, "index")), \
                 patch.object(R.sys, "platform", "darwin"), \
                 patch.object(P, "inspect_cli", return_value=(schema_fixture.contract(), "synthetic 1.2.3")), \
                 patch.object(P.subprocess, "Popen", side_effect=spawn), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(R.main(), 0)
            self.assertEqual(len(children), 1)
            self.assertEqual([r["method"] for r in children[0].requests], ["initialize", "thread/list", "thread/list"])
            self.assertEqual(children[0].command[-3:], ["app-server", "--listen", "stdio://"])
            self.assertEqual(children[0].terminate_count, 1)
            self.assertEqual(children[0].kill_count, 0)
            self.assertFalse((Path(temporary) / "synthetic-state.json").exists())

    def test_default_proxy_refusal_does_not_spawn_alternative(self):
        child = Mock()
        child.poll.return_value = None
        child.wait.return_value = 0
        def refused(reader):
            reader.messages.put({"transport_error": "synthetic websocket refusal"})
        with tempfile.TemporaryDirectory() as temporary:
            config = self.configuration(Path(temporary))
            config.pop("transport"); config.pop("start_local_server")
            with patch.object(P, "inspect_cli", return_value=(schema_fixture.contract(), "synthetic 1.2.3")), \
                 patch.object(P.subprocess, "Popen", return_value=child) as spawn, \
                 patch.object(P.Proxy, "_read", refused), patch.object(P.Proxy, "_write"):
                with self.assertRaises(ValueError): P.Proxy(config)
            self.assertEqual(spawn.call_count, 1)
            self.assertEqual(spawn.call_args.args[0][-2:], ["app-server", "proxy"])
            child.terminate.assert_called_once()

    def test_byte_budget_stops_in_second_message_without_overread(self):
        reader, stream = self.bare_reader(b'{"id":7}\n{"id":8}\n', 14)
        reader._read()
        messages = list(reader.messages.queue)
        self.assertEqual(stream.tell(), 14)
        self.assertEqual(reader.budget.received_bytes, 14)
        self.assertEqual(messages[1], {"id": 7})
        self.assertTrue(messages[2]["budget_exhausted"])

    def test_expired_time_budget_reads_zero_bytes(self):
        reader, stream = self.bare_reader(b'{"id":7}\n')
        reader.budget.deadline = time.monotonic() - 1
        reader._read()
        self.assertEqual(stream.tell(), 0)
        self.assertTrue(list(reader.messages.queue)[1]["budget_exhausted"])

    def test_time_exhausted_during_read_stops_before_json_decode(self):
        reader, _ = self.bare_reader(b"")
        class Expiring:
            def readline(self, limit):
                reader.budget.deadline = time.monotonic() - 1
                return b'{"id":9}\n'
        reader.process.stdout = Expiring()
        with patch.object(P.json, "loads", side_effect=AssertionError("decode after deadline")):
            reader._read()
        self.assertTrue(list(reader.messages.queue)[1]["budget_exhausted"])

    def test_message_limit_stops_before_next_bytes(self):
        reader, stream = self.bare_reader(b"{" + b" " * 30 + b"}\n", 100)
        with patch.object(P.codex_wire, "LIMIT", 16): reader._read()
        self.assertEqual(stream.tell(), 16)
        error = list(reader.messages.queue)[1]
        self.assertIn("oversized", error["transport_error"])
        self.assertFalse(error["budget_exhausted"])

    def test_non_object_message_stops(self):
        reader, stream = self.bare_reader(b'[1,2]\n{"id":7}\n')
        reader._read()
        self.assertEqual(stream.tell(), 6)
        self.assertIn("unknown stdio message schema", list(reader.messages.queue)[1]["transport_error"])

    def test_short_writes_preserve_exact_newline_frame(self):
        reader, _ = self.bare_reader(b"")
        reader.send_lock = threading.Lock()
        stored = bytearray()
        class ShortWriter:
            def write(self, data):
                piece = bytes(data[:3]); stored.extend(piece); return len(piece)
        reader.process.stdin = ShortWriter()
        reader._send(b'{"method":"initialized"}')
        self.assertEqual(bytes(stored), b'{"method":"initialized"}\n')

    def test_initialize_timeout_reaps_only_owned_child(self):
        children, unrelated = [], Mock()
        def spawn(*args, **kwargs):
            child = OwnedChild(*args, **kwargs); child.silent_initialize = True
            children.append(child); return child
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(P, "RPC_TIMEOUT", 0.05), \
                 patch.object(P, "inspect_cli", return_value=(schema_fixture.contract(), "synthetic 1.2.3")), \
                 patch.object(P.subprocess, "Popen", side_effect=spawn) as popen:
                with self.assertRaises(ValueError): P.Proxy(self.configuration(Path(temporary)))
            self.assertEqual(popen.call_count, 1)
            self.assertEqual(children[0].terminate_count, 1)
            self.assertEqual(children[0].kill_count, 0)
            unrelated.terminate.assert_not_called(); unrelated.kill.assert_not_called()

    def test_invalid_initialize_schema_reaps_child_before_history(self):
        children = []
        def spawn(*args, **kwargs):
            child = OwnedChild(*args, **kwargs); child.invalid_initialize = True
            children.append(child); return child
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(P, "inspect_cli", return_value=(schema_fixture.contract(), "synthetic 1.2.3")), \
                 patch.object(P.subprocess, "Popen", side_effect=spawn):
                with self.assertRaises(ValueError): P.Proxy(self.configuration(Path(temporary)))
            self.assertEqual([r["method"] for r in children[0].requests], ["initialize"])
            self.assertEqual(children[0].terminate_count, 1)

    def test_cleanup_kills_only_stubborn_owned_child(self):
        children = []
        def spawn(*args, **kwargs):
            child = OwnedChild(*args, **kwargs); child.stubborn = True
            children.append(child); return child
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(P, "inspect_cli", return_value=(schema_fixture.contract(), "synthetic 1.2.3")), \
                 patch.object(P.subprocess, "Popen", side_effect=spawn):
                reader = P.Proxy(self.configuration(Path(temporary)))
                reader.close(); reader.close()
            self.assertEqual((children[0].terminate_count, children[0].kill_count, children[0].wait_count), (1, 1, 2))

    def test_transport_binding_change_rejects_progress_before_spawn(self):
        bindings = []
        def capture(path, binding):
            bindings.append(dict(binding))
            raise ValueError("synthetic binding capture")
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(R, "Progress", side_effect=capture), patch.object(R.sys, "platform", "darwin"), \
                 patch.object(P.subprocess, "Popen") as spawn, contextlib.redirect_stdout(io.StringIO()):
                for transport, startup in (("proxy", False), ("local-stdio", True)):
                    with patch.object(sys, "argv", self.stage(temporary, "index", transport, startup)):
                        self.assertEqual(R.main(), 2)
                spawn.assert_not_called()
            self.assertNotIn("transport", bindings[0])
            local_without_transport = dict(bindings[1])
            self.assertEqual(local_without_transport.pop("transport"), "authorized-owned-local-stdio-v1")
            self.assertEqual(bindings[0], local_without_transport)
            progress_path = Path(temporary) / "synthetic-progress.json"
            progress = R.Progress(progress_path, bindings[0])
            progress.save("thread/list", {"limit": 1}, None, [], None)
            with patch.object(P.subprocess, "Popen") as spawn:
                with self.assertRaises(ValueError): R.Progress(progress_path, bindings[1])
                spawn.assert_not_called()

    def test_local_read_methods_rejected_before_schema_or_send(self):
        reader, _ = self.bare_reader(b"")
        reader.contract = Mock()
        reader._send = Mock()
        reader.sequence = 0
        for method in ("thread/read", "thread/turns/list", "thread/items/list"):
            with self.subTest(method=method):
                with self.assertRaisesRegex(ValueError, "cross-process live status is unverified"):
                    reader.call(method, {})
        reader.contract.validate_request.assert_not_called()
        reader._send.assert_not_called()
        self.assertEqual(reader.sequence, 0)

    def test_non_boolean_startup_opt_in_rejected_before_cli(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = self.configuration(Path(temporary))
            config["start_local_server"] = 1
            with patch.object(P, "inspect_cli") as inspect, patch.object(P.subprocess, "Popen") as spawn:
                with self.assertRaises(ValueError): P.Proxy(config)
                inspect.assert_not_called(); spawn.assert_not_called()


if __name__ == "__main__": unittest.main()
