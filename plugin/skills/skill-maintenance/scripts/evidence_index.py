"""Index explicit outcomes in caller-authorized, already exported evidence."""
import hashlib
import json
import argparse
import os
import stat
from contextlib import ExitStack, contextmanager
from pathlib import Path


LABELS = ("rework", "unnecessary_retry", "out_of_scope_write", "normal_hold", "expected_failure")


def source_path(value):
    path = Path(value).absolute()
    try:
        resolved = path.resolve()
    except RuntimeError as error:
        raise ValueError("cyclic symbolic link") from error
    if path != resolved or not path.is_file():
        raise ValueError("input must be a canonical regular file without symbolic links")
    return path


def checked_source(value):
    path = Path(value).absolute()
    before = stat_version(path.stat(follow_symlinks=False))
    return source_path(path), before


def directory_fd(path, outside_git=False):
    """Pin every directory component; never follow a replaced parent symlink."""
    path = Path(path).absolute()
    if ".." in path.parts:
        raise ValueError("canonical directory required")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open(path.anchor, flags)
    try:
        for part in path.parts[1:]:
            child = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = child
            if outside_git:
                try:
                    os.stat(".git", dir_fd=fd, follow_symlinks=False)
                except FileNotFoundError:
                    pass
                else:
                    raise ValueError("private output must be outside every Git checkout")
        return fd
    except BaseException:
        os.close(fd)
        raise


@contextmanager
def open_source(path, expected=None):
    path = Path(path)
    parent = directory_fd(path.parent)
    try:
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    finally:
        os.close(parent)
    with os.fdopen(fd, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("regular input file required")
        if expected is not None and version(stream) != expected:
            raise ValueError("input identity or version changed before open")
        yield stream


def stream_digest(stream):
    stream.seek(0)
    digest = hashlib.sha256()
    for chunk in iter(lambda: stream.read(65536), b""):
        digest.update(chunk)
    stream.seek(0)
    return digest.hexdigest()


def fingerprint(path):
    path, expected = checked_source(path)
    with open_source(path, expected) as stream:
        return stream_digest(stream)


def result_fields(output):
    if isinstance(output, str):
        try:
            output = json.loads(output)
        except ValueError:
            output = None
    if not isinstance(output, dict):
        output = {}
    return {"exit_code": output.get("exit_code") if type(output.get("exit_code")) is int else None,
            "isError": output.get("isError") if type(output.get("isError")) is bool else None}


def outcome(output):
    fields = result_fields(output)
    if fields["isError"] is True:
        return "failure"
    code = fields["exit_code"]
    if code is not None:
        return "success" if code == 0 else "failure"
    return "unknown"


def scan_export(path):
    path, expected = checked_source(path)
    with open_source(path, expected) as stream:
        yield from scan_stream(stream, stream_digest(stream))


def scan_stream(stream, ident):
    for number, line in enumerate(stream, 1):
        event = {"ref": f"{ident}:{number}", "line": number, "source": "observed"}
        try:
            row = json.loads(line)
            payload = row["payload"]
            if not isinstance(payload, dict):
                raise ValueError("invalid payload")
            kind = payload.get("type")
            event["source_line"] = row.get("line") if type(row.get("line")) is int else None
            call_id = payload.get("call_id") if isinstance(payload.get("call_id"), str) else None
            if kind in {"function_call", "custom_tool_call"}:
                yield {**event, "kind": "tool_call", "tool": payload.get("name")
                       if isinstance(payload.get("name"), str) else None, "call_id": call_id}
            elif kind in {"function_call_output", "custom_tool_call_output"}:
                fields = result_fields(payload.get("output"))
                yield {**event, "kind": "tool_result", "call_id": call_id,
                       **fields, "outcome": outcome(fields)}
            elif isinstance(kind, str) and kind.endswith("_output"):
                yield {**event, "kind": "tool_result", "call_id": call_id, "outcome": "unknown",
                       "exit_code": None, "isError": None}
            elif kind == "message" and payload.get("role") == "user":
                yield {**event, "kind": "user_input"}
            else:
                yield {**event, "kind": "other"}
        except (ValueError, TypeError, KeyError, UnicodeError):
            yield {**event, "kind": "unreadable", "outcome": "unknown"}


def stat_version(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def version(stream):
    return stat_version(os.fstat(stream.fileno()))


def distinct_keys(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate annotation key")
        value[key] = item
    return value


def changed(path, stream, before, sha):
    same_contents = stream_digest(stream) == sha and version(stream) == before
    try:
        with open_source(path) as current:
            return not same_contents or version(current) != before
    except (OSError, ValueError):
        return True


@contextmanager
def private_file(folder_fd, name):
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=folder_fd)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        yield stream


def index(exports, reports, annotations, output, repo):
    with ExitStack() as stack:
        return build_index(stack, exports, reports, annotations, output, repo)


def build_index(stack, exports, reports, annotations, output, repo):
    inputs = [(*checked_source(p), "observed") for p in exports]
    inputs += [(*checked_source(p), "self_report") for p in reports]
    versions = []
    for path, expected, basis in inputs:
        stream = stack.enter_context(open_source(path, expected))
        before = version(stream)
        versions.append((path, basis, stream, before, stream_digest(stream)))
    if len({sha for _, _, _, _, sha in versions}) != len(versions):
        raise ValueError("duplicate evidence content; correlate once instead of counting twice")
    note_source = None
    if annotations:
        path, expected = checked_source(annotations)
        stream = stack.enter_context(open_source(path, expected))
        note_source = (path, stream, version(stream), stream_digest(stream))
        notes = json.load(stream, object_pairs_hook=distinct_keys)
    else:
        notes = {}
    if not isinstance(notes, dict):
        raise ValueError("annotations must map evidence references to labels and reasons")
    for ref, note in notes.items():
        if (not isinstance(note, dict) or set(note) != {"labels", "reason"}
                or not isinstance(note["labels"], list) or not note["labels"]
                or any(not isinstance(x, str) or x not in LABELS for x in note["labels"])
                or len(set(note["labels"])) != len(note["labels"])
                or not isinstance(note["reason"], str) or not note["reason"].strip()):
            raise ValueError("annotation needs supported distinct labels and a reason")
    output, repo = Path(output).absolute(), Path(repo).resolve()
    parent_identity = stat_version(output.parent.stat(follow_symlinks=False))[:2]
    try:
        resolved = output.resolve()
    except RuntimeError as error:
        raise ValueError("cyclic output symbolic link") from error
    if output != resolved or resolved == repo or repo in resolved.parents:
        raise ValueError("private output must be canonical and outside improvement repository")
    if any(p.name == ".git" or (p / ".git").exists() for p in (resolved, *resolved.parents)):
        raise ValueError("private output must be outside every Git checkout")
    parent = directory_fd(output.parent, outside_git=True)
    try:
        if stat_version(os.fstat(parent))[:2] != parent_identity:
            raise ValueError("output parent identity changed before creation")
        os.mkdir(output.name, mode=0o700, dir_fd=parent)
        folder_fd = os.open(output.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
    finally:
        os.close(parent)
    stack.callback(os.close, folder_fd)
    os.fchmod(folder_fd, 0o700)
    counts = {key: 0 for key in ("records", "tool_calls", "tool_results_failure",
              "tool_results_success", "tool_results_unknown", "user_inputs", "unreadable",
              "other", "self_report_documents", "unclassified_results")}
    labels = dict.fromkeys(LABELS, 0)
    seen = set()
    sources = []
    with private_file(folder_fd, "events.jsonl") as sink:
        for path, basis, stream, before, sha in versions:
            source_records = 0
            events = scan_stream(stream, sha) if basis == "observed" else iter([
                {"ref": f"{sha}:document", "source": basis, "kind": "self_report"}])
            for event in events:
                source_records += 1
                counts["records"] += 1
                kind = event["kind"]
                key = {"tool_call": "tool_calls", "tool_result": "tool_results_" + event.get("outcome", "unknown"),
                       "user_input": "user_inputs", "self_report": "self_report_documents"}.get(kind, kind)
                counts[key] += 1
                note = notes.get(event["ref"])
                if note:
                    event["classification"] = note
                    seen.add(event["ref"])
                    for label in note["labels"]:
                        labels[label] += 1
                elif kind == "tool_result":
                    counts["unclassified_results"] += 1
                sink.write(json.dumps(event, ensure_ascii=False) + "\n")
            sources.append({"sha256": sha, "basis": basis,
                            "empty_export": basis == "observed" and source_records == 0,
                            "changed_during_read": changed(path, stream, before, sha)})
    note_version = ({"sha256": note_source[3], "changed_during_read": changed(*note_source)}
                    if note_source else None)
    tool_results = sum(counts["tool_results_" + value] for value in ("failure", "success", "unknown"))
    if not tool_results:
        for value in ("failure", "success", "unknown"):
            counts["tool_results_" + value] = None
    summary = {"version": 1, "sources": sources, "counts": counts, "classifications": labels,
               "annotations": note_version, "tool_result_evidence": "available" if tool_results else "unavailable",
               "unmatched_annotations": sorted(set(notes) - seen), "full_context_read_verified": False,
               "status": "partial" if (counts["unreadable"] or set(notes) - seen
                         or any(s["changed_during_read"] or s["empty_export"] for s in sources)
                         or note_version and note_version["changed_during_read"]) else "indexed"}
    with private_file(folder_fd, "summary.json") as stream:
        json.dump(summary, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export", action="append", default=[])
    parser.add_argument("--self-report", action="append", default=[])
    parser.add_argument("--annotations")
    parser.add_argument("--output", required=True)
    parser.add_argument("--repo", required=True)
    args = parser.parse_args()
    if not args.export and not args.self_report:
        parser.error("at least one caller-authorized export or self-report is required")
    try:
        summary = index(args.export, args.self_report, args.annotations, args.output, args.repo)
    except (ValueError, OSError) as error:
        parser.exit(2, type(error).__name__ + ": evidence index not completed\n")
    print(json.dumps({"status": summary["status"], "counts": summary["counts"]}))
    return 0 if summary["status"] == "indexed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
