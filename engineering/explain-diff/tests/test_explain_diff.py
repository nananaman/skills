from __future__ import annotations

import json
import base64
from contextlib import redirect_stdout
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SKILL_DIR = Path(__file__).resolve().parent.parent
CLI = SKILL_DIR / "scripts" / "explain-diff.py"
TEMPLATE = SKILL_DIR / "assets" / "report-template.html"
PACKAGE = SKILL_DIR / "package.json"
SPEC = importlib.util.spec_from_file_location("explain_diff", CLI)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class FakeHttpServer:
    created_address: tuple[str, int] | None = None
    served = False
    closed = False

    def __init__(self, address: tuple[str, int], handler: object) -> None:
        type(self).created_address = address
        self.server_address = (address[0], 43123)
        self.handler = handler

    def serve_forever(self) -> None:
        type(self).served = True
        raise KeyboardInterrupt

    def server_close(self) -> None:
        type(self).closed = True


class ExplainDiffCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self._git("init", "-q")
        self._git("config", "user.name", "Explain Diff Test")
        self._git("config", "user.email", "explain-diff@example.com")
        (self.repo / "mixed.txt").write_text("base\n", encoding="utf-8")
        (self.repo / "unstaged.txt").write_text("base\n", encoding="utf-8")
        self._git("add", "mixed.txt", "unstaged.txt")
        self._git("commit", "-qm", "base")
        FakeHttpServer.created_address = None
        FakeHttpServer.served = False
        FakeHttpServer.closed = False

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(self.repo), *args],
            text=True,
            capture_output=True,
            check=True,
        )

    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["python3", str(CLI), *args],
            cwd=self.repo,
            text=True,
            capture_output=True,
            check=False,
        )

    def _snapshot_with_one_change(self) -> tuple[Path, dict[str, object]]:
        (self.repo / "mixed.txt").write_text("base\nchanged\n", encoding="utf-8")
        output = self.root / "snapshot.json"
        result = self._run("snapshot", "--output", str(output))
        self.assertEqual(0, result.returncode, result.stderr)
        return output, json.loads(output.read_text(encoding="utf-8"))

    def _write_manifest(
        self,
        snapshot: dict[str, object],
        *,
        hunk_ids: list[str] | None = None,
    ) -> Path:
        selected = hunk_ids if hunk_ids is not None else [hunk["id"] for hunk in snapshot["hunks"]]
        manifest = {
            "version": 1,
            "title": "Example local diff",
            "groups": [
                {
                    "id": "behavior",
                    "title": "Behavior change",
                    "summary": "A concise summary.",
                    "intent": "Explain why the implementation changed.",
                    "impact": "The local example only.",
                    "kind": "implementation",
                    "risk": "注意",
                    "risk_reason": "The behavior changes.",
                    "needs_improvement": False,
                    "needs_improvement_reason": "",
                    "hunk_ids": selected,
                }
            ],
        }
        path = self.root / "manifest.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        return path

    def _read_report_data(self, report: Path) -> dict[str, object]:
        html = report.read_text(encoding="utf-8")
        start_marker = '<script id="report-data" type="application/octet-stream">'
        encoded = html.split(start_marker, 1)[1].split("</script>", 1)[0]
        return json.loads(base64.b64decode(encoded).decode("utf-8"))

    def test_snapshot_collects_all_local_change_sources_without_mutating_git_state(self) -> None:
        # Arrange: staged・unstaged の両方を持つファイルと、別の未追跡ファイルを用意する。
        (self.repo / "mixed.txt").write_text("base\nstaged\n", encoding="utf-8")
        self._git("add", "mixed.txt")
        (self.repo / "mixed.txt").write_text("base\nstaged\nunstaged\n", encoding="utf-8")
        (self.repo / "unstaged.txt").write_text("base\nchanged\n", encoding="utf-8")
        (self.repo / "untracked.txt").write_text("new\n", encoding="utf-8")
        before = self._git("status", "--porcelain=v1", "--untracked-files=all").stdout
        output = self.root / "snapshot.json"

        # Act: 公開 CLI からローカル差分の snapshot を収集する。
        result = self._run("snapshot", "--output", str(output))

        # Assert: すべての変更元を収集し、Git の状態は変更しない。
        self.assertEqual(0, result.returncode, result.stderr)
        snapshot = json.loads(output.read_text(encoding="utf-8"))
        sources_by_path = {
            (entry["source"], entry["path"])
            for entry in snapshot["entries"]
        }
        self.assertIn(("staged", "mixed.txt"), sources_by_path)
        self.assertIn(("unstaged", "mixed.txt"), sources_by_path)
        self.assertIn(("unstaged", "unstaged.txt"), sources_by_path)
        self.assertIn(("untracked", "untracked.txt"), sources_by_path)
        self.assertEqual(before, self._git("status", "--porcelain=v1", "--untracked-files=all").stdout)

    def test_snapshot_exposes_stable_hunk_inventory_and_summary_statistics(self) -> None:
        # Arrange: 別々の hunk になる 2 つのテキスト変更を作る。
        (self.repo / "mixed.txt").write_text("base\nadded\n", encoding="utf-8")
        (self.repo / "new.txt").write_text("first\nsecond\n", encoding="utf-8")
        first_output = self.root / "first.json"
        second_output = self.root / "second.json"

        # Act: 同一のローカル差分を 2 回収集する。
        first_result = self._run("snapshot", "--output", str(first_output))
        second_result = self._run("snapshot", "--output", str(second_output))

        # Assert: 公開 inventory が完全かつ安定し、レポート用統計を含む。
        self.assertEqual(0, first_result.returncode, first_result.stderr)
        self.assertEqual(0, second_result.returncode, second_result.stderr)
        first = json.loads(first_output.read_text(encoding="utf-8"))
        second = json.loads(second_output.read_text(encoding="utf-8"))
        self.assertEqual(first["fingerprint"], second["fingerprint"])
        self.assertEqual(first["hunks"], second["hunks"])
        self.assertEqual(2, first["stats"]["files"])
        self.assertEqual(2, first["stats"]["hunks"])
        self.assertEqual(3, first["stats"]["additions"])
        self.assertEqual(0, first["stats"]["deletions"])
        self.assertEqual({"mixed.txt", "new.txt"}, {hunk["path"] for hunk in first["hunks"]})

    def test_snapshot_fingerprint_distinguishes_invalid_utf8_bytes(self) -> None:
        # Arrange: 表示不能になる異なる非UTF-8 byteを用意する。
        path = self.repo / "invalid.txt"
        path.write_bytes(b"\x80\n")
        first_output = self.root / "invalid-first.json"
        second_output = self.root / "invalid-second.json"

        # Act: byteだけを別の無効値へ変えて、それぞれsnapshotを作る。
        first_result = self._run("snapshot", "--output", str(first_output))
        path.write_bytes(b"\x81\n")
        second_result = self._run("snapshot", "--output", str(second_output))

        # Assert: 共通の表示不能metadataでもfingerprintは元byteの違いを保持する。
        self.assertEqual(0, first_result.returncode, first_result.stderr)
        self.assertEqual(0, second_result.returncode, second_result.stderr)
        first = json.loads(first_output.read_text(encoding="utf-8"))
        second = json.loads(second_output.read_text(encoding="utf-8"))
        self.assertTrue(first["entries"][0]["binary"])
        self.assertIn("Undisplayable non-UTF-8 file", first["entries"][0]["raw_diff"])
        self.assertEqual(first["entries"][0]["raw_diff"], second["entries"][0]["raw_diff"])
        self.assertNotEqual(first["fingerprint"], second["fingerprint"])

    def test_snapshot_fingerprint_distinguishes_branches_with_the_same_diff(self) -> None:
        # Arrange: 同じlocal差分を持つmain branchのsnapshotを作る。
        (self.repo / "mixed.txt").write_text("base\nchanged\n", encoding="utf-8")
        main_output = self.root / "main.json"
        branch_output = self.root / "branch.json"
        main_result = self._run("snapshot", "--output", str(main_output))

        # Act: local差分を保ったまま別branchへ切り替えてsnapshotを作る。
        self._git("switch", "-c", "other-review-target")
        branch_result = self._run("snapshot", "--output", str(branch_output))

        # Assert: diff内容が同じでもreview対象branchが違えばfingerprintを分ける。
        self.assertEqual(0, main_result.returncode, main_result.stderr)
        self.assertEqual(0, branch_result.returncode, branch_result.stderr)
        main_snapshot = json.loads(main_output.read_text(encoding="utf-8"))
        branch_snapshot = json.loads(branch_output.read_text(encoding="utf-8"))
        self.assertEqual(main_snapshot["entries"], branch_snapshot["entries"])
        self.assertNotEqual(main_snapshot["fingerprint"], branch_snapshot["fingerprint"])

    def test_snapshot_preserves_both_paths_of_a_staged_rename(self) -> None:
        # Arrange: 追跡済みfileを内容変更なしでrenameしてstageする。
        self._git("mv", "mixed.txt", "renamed.txt")
        output = self.root / "rename.json"

        # Act: staged renameをsnapshotへ収集する。
        result = self._run("snapshot", "--output", str(output))

        # Assert: rename metadataと新旧両pathをreview対象へ残す。
        self.assertEqual(0, result.returncode, result.stderr)
        snapshot = json.loads(output.read_text(encoding="utf-8"))
        raw_diff = "\n".join(entry["raw_diff"] for entry in snapshot["entries"])
        self.assertIn("rename from mixed.txt", raw_diff)
        self.assertIn("rename to renamed.txt", raw_diff)

    def test_snapshot_marks_a_tracked_binary_change(self) -> None:
        # Arrange: binary fileをcommitしてから内容を変更する。
        binary = self.repo / "image.bin"
        binary.write_bytes(b"\x00\x01original")
        self._git("add", "image.bin")
        self._git("commit", "-m", "add binary")
        binary.write_bytes(b"\x00\x02changed")
        output = self.root / "binary.json"

        # Act: tracked binary差分をsnapshotへ収集する。
        result = self._run("snapshot", "--output", str(output))

        # Assert: ASCII表現のGit binary patchでもbinaryとして識別する。
        self.assertEqual(0, result.returncode, result.stderr)
        snapshot = json.loads(output.read_text(encoding="utf-8"))
        entry = next(item for item in snapshot["entries"] if item["path"] == "image.bin")
        self.assertTrue(entry["binary"])
        self.assertIn("GIT binary patch", entry["raw_diff"])

    def test_snapshot_escapes_newlines_in_an_untracked_symlink_target(self) -> None:
        # Arrange: diff hunk headerに見える改行を含む参照先のsymlinkを作る。
        os.symlink("target\n@@ -1 +1 @@\nvalue", self.repo / "multiline-link")
        output = self.root / "symlink-newline.json"

        # Act: 未追跡symlinkをsnapshotへ収集する。
        result = self._run("snapshot", "--output", str(output))

        # Assert: targetを単一行へescapeし、偽hunkを作らない。
        self.assertEqual(0, result.returncode, result.stderr)
        snapshot = json.loads(output.read_text(encoding="utf-8"))
        entry = next(item for item in snapshot["entries"] if item["path"] == "multiline-link")
        self.assertEqual(1, len(entry["hunks"]))
        self.assertIn(r"\n@@ -1 +1 @@\n", entry["raw_diff"])

    def test_snapshot_serializes_a_non_utf8_path(self) -> None:
        # Arrange: Git pathのsurrogateescapeと同じ文字列を持つpayloadを用意する。
        payload = {"path": "invalid-\udcff.txt"}

        # Act: snapshotと同じserializerでJSONへ変換する。
        serialized = MODULE.serialize_json(payload)

        # Assert: surrogateを直接encodeせずUnicode escapeへ変換する。
        self.assertIn(r"\udcff", serialized)
        serialized.encode("utf-8")

    def test_parse_hunks_assigns_unique_ids_to_identical_hunks(self) -> None:
        # Arrange: 同一内容のhunkが同じfile内に2つあるdiffを用意する。
        raw_diff = "@@ -1 +1 @@\n-old\n+new\n@@ -10 +10 @@\n-old\n+new\n"

        # Act: 公開snapshotと同じparserでhunkへ分割する。
        hunks = MODULE.parse_hunks("unstaged", "repeated.txt", raw_diff)

        # Assert: 内容が同じでもfile内の位置で一意なIDを割り当てる。
        self.assertEqual(2, len(hunks))
        self.assertEqual(2, len({hunk["id"] for hunk in hunks}))

    def test_render_accepts_a_manifest_that_assigns_every_hunk_once(self) -> None:
        # Arrange: snapshot と全 hunk を割り当てた manifest を作る。
        snapshot_path, snapshot = self._snapshot_with_one_change()
        manifest_path = self._write_manifest(snapshot)
        report = self.root / "report.html"

        # Act: ブラウザを開かず自己完結したレポートを生成する。
        result = self._run(
            "render",
            "--snapshot",
            str(snapshot_path),
            "--manifest",
            str(manifest_path),
            "--output",
            str(report),
            "--no-open",
        )

        # Assert: 完全な manifest からブラウザ用 artifact が生成される。
        self.assertEqual(0, result.returncode, result.stderr)
        html = report.read_text(encoding="utf-8")
        self.assertIn('data-explain-diff-report="1"', html)
        self.assertIn(snapshot["fingerprint"], html)

    def test_render_rejects_an_unignored_output_inside_the_worktree(self) -> None:
        # Arrange: 現在のsnapshotと完全なmanifestを用意する。
        snapshot_path, snapshot = self._snapshot_with_one_change()
        manifest_path = self._write_manifest(snapshot)
        report = self.repo / "report.html"

        # Act: local差分へ混入するworktree内pathを出力先に指定する。
        result = self._run(
            "render",
            "--snapshot",
            str(snapshot_path),
            "--manifest",
            str(manifest_path),
            "--output",
            str(report),
            "--no-open",
        )

        # Assert: fingerprintを生成直後にstaleへする出力を拒否する。
        self.assertNotEqual(0, result.returncode)
        self.assertIn("output inside repository must be ignored", result.stderr)
        self.assertFalse(report.exists())

    def test_render_allows_output_in_the_repository_git_directory(self) -> None:
        # Arrange: 通常workflowと同じGit artifact directoryを出力先にする。
        snapshot_path, snapshot = self._snapshot_with_one_change()
        manifest_path = self._write_manifest(snapshot)
        git_dir = Path(self._git("rev-parse", "--path-format=absolute", "--git-dir").stdout.strip())
        report = git_dir / "explain-diff" / snapshot["fingerprint"] / "report.html"

        # Act: worktree差分へ混入しないGit directoryへreportを生成する。
        result = self._run(
            "render",
            "--snapshot",
            str(snapshot_path),
            "--manifest",
            str(manifest_path),
            "--output",
            str(report),
            "--no-open",
        )

        # Assert: 既定artifact lifecycleと整合する出力先を許可する。
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue(report.exists())

    def test_render_rejects_a_manifest_with_an_unassigned_hunk(self) -> None:
        # Arrange: 2つのhunkを含むsnapshotを作り、片方だけをgroupへ割り当てる。
        (self.repo / "mixed.txt").write_text("base\nchanged\n", encoding="utf-8")
        (self.repo / "untracked.txt").write_text("new\n", encoding="utf-8")
        snapshot_path = self.root / "snapshot.json"
        snapshot_result = self._run("snapshot", "--output", str(snapshot_path))
        self.assertEqual(0, snapshot_result.returncode, snapshot_result.stderr)
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        manifest_path = self._write_manifest(snapshot, hunk_ids=[snapshot["hunks"][0]["id"]])

        # Act: 公開 render コマンドから検証する。
        result = self._run(
            "render",
            "--snapshot",
            str(snapshot_path),
            "--manifest",
            str(manifest_path),
            "--output",
            str(self.root / "report.html"),
            "--no-open",
        )

        # Assert: coverage 不足なら artifact を生成しない。
        self.assertNotEqual(0, result.returncode)
        self.assertIn("unassigned", result.stderr)
        self.assertFalse((self.root / "report.html").exists())

    def test_render_rejects_an_empty_change_group(self) -> None:
        # Arrange: 全hunkを有効groupへ割り当てつつ、空groupも追加する。
        snapshot_path, snapshot = self._snapshot_with_one_change()
        manifest_path = self._write_manifest(snapshot)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["groups"].append({
            **manifest["groups"][0],
            "id": "empty-group",
            "title": "Empty group",
            "hunk_ids": [],
        })
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        # Act: 空groupを含むmanifestを生成へ渡す。
        result = self._run(
            "render",
            "--snapshot",
            str(snapshot_path),
            "--manifest",
            str(manifest_path),
            "--output",
            str(self.root / "empty-group.html"),
            "--no-open",
        )

        # Assert: hunkを持たない確認対象をreportへ出さない。
        self.assertNotEqual(0, result.returncode)
        self.assertIn("hunk_ids must be a non-empty list", result.stderr)

    def test_render_rejects_a_manifest_without_a_report_title(self) -> None:
        # Arrange: hunk coverage を保ったまま、画面上のレポート名を空にする。
        snapshot_path, snapshot = self._snapshot_with_one_change()
        manifest_path = self._write_manifest(snapshot)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["title"] = ""
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        # Act: top-level 契約を満たさない manifest を生成に渡す。
        result = self._run(
            "render",
            "--snapshot",
            str(snapshot_path),
            "--manifest",
            str(manifest_path),
            "--output",
            str(self.root / "untitled.html"),
            "--no-open",
        )

        # Assert: 未定義または空のタイトルを持つレポートは生成しない。
        self.assertNotEqual(0, result.returncode)
        self.assertIn("title", result.stderr)
        self.assertFalse((self.root / "untitled.html").exists())

    def test_render_accepts_a_mermaid_flowchart(self) -> None:
        # Arrange: flowchartとreview対象へのnode linkを定義する。
        snapshot_path, snapshot = self._snapshot_with_one_change()
        manifest_path = self._write_manifest(snapshot)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["diagrams"] = [{
            "id": "flow",
            "title": "処理flow",
            "description": "入口から出力までを示す。",
            "format": "mermaid",
            "diagram_kind": "flowchart",
            "source": "flowchart TB\n  input -->|passes data| output",
            "node_links": [{
                "node_id": "output",
                "group_ids": ["behavior"],
                "hunk_ids": [snapshot["hunks"][0]["id"]],
                "term_ids": [],
            }],
        }]
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        # Act: Mermaidを含むreportを生成する。
        result = self._run("render", "--snapshot", str(snapshot_path), "--manifest",
                           str(manifest_path), "--output", str(self.root / "mermaid.html"), "--no-open")

        # Assert: Mermaid sourceと固定bundleが自己完結reportへ入る。
        self.assertEqual(0, result.returncode, result.stderr)
        html = (self.root / "mermaid.html").read_text(encoding="utf-8")
        self.assertIn("flowchart TB", self._read_report_data(self.root / "mermaid.html")["manifest"]["diagrams"][0]["source"])
        self.assertNotIn("__MERMAID_JS__", html)

    def test_render_rejects_a_diagram_hunk_linked_to_another_group(self) -> None:
        # Arrange: 2つのgroupを作り、図では片方のgroupから他方のhunkを参照する。
        (self.repo / "mixed.txt").write_text("base\nchanged\n", encoding="utf-8")
        (self.repo / "untracked.txt").write_text("new\n", encoding="utf-8")
        snapshot_path = self.root / "snapshot.json"
        snapshot_result = self._run("snapshot", "--output", str(snapshot_path))
        self.assertEqual(0, snapshot_result.returncode, snapshot_result.stderr)
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        manifest_path = self._write_manifest(snapshot, hunk_ids=[snapshot["hunks"][0]["id"]])
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["groups"].append({
            **manifest["groups"][0],
            "id": "second-group",
            "title": "Second group",
            "hunk_ids": [snapshot["hunks"][1]["id"]],
        })
        manifest["diagrams"] = [{
            "id": "flow",
            "title": "処理flow",
            "description": "不整合なreview対象へのlink。",
            "format": "mermaid",
            "diagram_kind": "flowchart",
            "source": "flowchart TB\n  input --> output",
            "node_links": [{
                "node_id": "output",
                "group_ids": ["behavior"],
                "hunk_ids": [snapshot["hunks"][1]["id"]],
                "term_ids": [],
            }],
        }]
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        # Act: 不整合なnode linkを含むmanifestをrenderする。
        result = self._run(
            "render",
            "--snapshot",
            str(snapshot_path),
            "--manifest",
            str(manifest_path),
            "--output",
            str(self.root / "invalid-link.html"),
            "--no-open",
        )

        # Assert: 表示されないhunkへのnavigationを生成前に拒否する。
        self.assertNotEqual(0, result.returncode)
        self.assertIn("hunk does not belong to linked group", result.stderr)

    def test_render_rejects_node_links_for_a_non_flowchart_diagram(self) -> None:
        # Arrange: state diagramにreview対象へのnode linkを定義する。
        snapshot_path, snapshot = self._snapshot_with_one_change()
        manifest_path = self._write_manifest(snapshot)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["diagrams"] = [{
            "id": "state",
            "title": "状態遷移",
            "description": "状態の変化を示す。",
            "format": "mermaid",
            "diagram_kind": "stateDiagram-v2",
            "source": "stateDiagram-v2\n  [*] --> Ready",
            "node_links": [{
                "node_id": "Ready",
                "group_ids": ["behavior"],
                "hunk_ids": [snapshot["hunks"][0]["id"]],
                "term_ids": [],
            }],
        }]
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        # Act: Mermaidの不安定なDOM IDに依存するnode linkをrenderする。
        result = self._run(
            "render",
            "--snapshot",
            str(snapshot_path),
            "--manifest",
            str(manifest_path),
            "--output",
            str(self.root / "state-link.html"),
            "--no-open",
        )

        # Assert: navigation契約を保証できるflowchart以外ではnode linkを拒否する。
        self.assertNotEqual(0, result.returncode)
        self.assertIn("node_links are supported only for flowchart", result.stderr)

    def test_render_rejects_a_non_mermaid_diagram(self) -> None:
        # Arrange: 初版contractにない旧diagram形式をmanifestへ入れる。
        snapshot_path, snapshot = self._snapshot_with_one_change()
        manifest_path = self._write_manifest(snapshot)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["diagrams"] = [{
            "id": "legacy",
            "title": "Legacy diagram",
            "description": "Unsupported format.",
            "type": "code-impact",
        }]
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        # Act: Mermaidではないdiagramを生成へ渡す。
        result = self._run(
            "render",
            "--snapshot",
            str(snapshot_path),
            "--manifest",
            str(manifest_path),
            "--output",
            str(self.root / "legacy.html"),
            "--no-open",
        )

        # Assert: diagram contractをMermaidだけに保つ。
        self.assertNotEqual(0, result.returncode)
        self.assertIn("format must be mermaid", result.stderr)

    def test_render_rejects_a_glossary_id_with_whitespace(self) -> None:
        # Arrange: DOM data属性で安全に往復できない空白入り用語IDを定義する。
        snapshot_path, snapshot = self._snapshot_with_one_change()
        manifest_path = self._write_manifest(snapshot)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["glossary"] = [{
            "id": "invalid term",
            "term": "Invalid",
            "definition": "空白を含むID。",
        }]
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        # Act: 不正な用語IDを含むmanifestをrenderする。
        result = self._run(
            "render",
            "--snapshot",
            str(snapshot_path),
            "--manifest",
            str(manifest_path),
            "--output",
            str(self.root / "invalid-term.html"),
            "--no-open",
        )

        # Assert: node linkが壊れるIDを生成前に拒否する。
        self.assertNotEqual(0, result.returncode)
        self.assertIn("glossary id must be dash-case", result.stderr)

    def test_mermaid_runtime_is_managed_as_a_node_dependency(self) -> None:
        # Arrange & Act: report生成に必要なfrontend依存の公開契約を読む。
        package = json.loads(PACKAGE.read_text(encoding="utf-8"))

        # Assert: Mermaidはversion固定されたdependencyで、vendor copyをsource管理しない。
        self.assertEqual("11.16.0", package["dependencies"]["mermaid"])
        self.assertFalse((SKILL_DIR / "assets" / "vendor" / "mermaid-11.16.0.min.js").exists())
        self.assertFalse((SKILL_DIR / "assets" / "vendor" / "MERMAID-LICENSE").exists())

    def test_syntax_highlighting_is_provided_by_prism(self) -> None:
        # Arrange & Act: frontend依存と自己完結reportのhighlight契約を読む。
        package = json.loads(PACKAGE.read_text(encoding="utf-8"))
        template = TEMPLATE.read_text(encoding="utf-8")

        # Assert: Prismをversion固定し、独自tokenizerではなくlanguage grammarを使う。
        self.assertEqual("1.30.0", package["dependencies"]["prismjs"])
        self.assertIn("__PRISM_JS__", template)
        self.assertIn("Prism.highlight(", template)
        self.assertIn("Prism.languages[language]", template)
        self.assertNotIn("const keywordSets =", template)

    def test_render_rejects_a_group_id_that_is_not_dash_case(self) -> None:
        # Arrange: filterの空白区切り表現を壊すgroup IDを作る。
        snapshot_path, snapshot = self._snapshot_with_one_change()
        manifest_path = self._write_manifest(snapshot)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["groups"][0]["id"] = "group one"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        # Act: dash-caseではないgroup IDを生成へ渡す。
        result = self._run(
            "render",
            "--snapshot",
            str(snapshot_path),
            "--manifest",
            str(manifest_path),
            "--output",
            str(self.root / "invalid-group-id.html"),
            "--no-open",
        )

        # Assert: filter・storage keyとして安全でないgroup IDを拒否する。
        self.assertNotEqual(0, result.returncode)
        self.assertIn("group id must be dash-case", result.stderr)

    def test_render_rejects_a_snapshot_after_the_local_diff_changes(self) -> None:
        # Arrange: 完全な manifest を作った後で snapshot を stale にする。
        snapshot_path, snapshot = self._snapshot_with_one_change()
        manifest_path = self._write_manifest(snapshot)
        (self.repo / "mixed.txt").write_text("base\nnewer change\n", encoding="utf-8")
        report = self.root / "stale-report.html"

        # Act: 古くなった snapshot の生成を試みる。
        result = self._run(
            "render",
            "--snapshot",
            str(snapshot_path),
            "--manifest",
            str(manifest_path),
            "--output",
            str(report),
            "--no-open",
        )

        # Assert: 差分が変化した worktree のレビューページは生成しない。
        self.assertNotEqual(0, result.returncode)
        self.assertIn("stale", result.stderr)
        self.assertFalse(report.exists())

    def test_render_orders_groups_by_improvement_risk_and_impact(self) -> None:
        # Arrange: 現在の hunk を 3 つ作り、公開される並び順の契約を分離する。
        for path in ("low.txt", "high.txt", "improve.txt"):
            (self.repo / path).write_text(f"{path}\n", encoding="utf-8")
        snapshot_path = self.root / "ordered-snapshot.json"
        snapshot_result = self._run("snapshot", "--output", str(snapshot_path))
        self.assertEqual(0, snapshot_result.returncode, snapshot_result.stderr)
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        hunk_id_by_path = {hunk["path"]: hunk["id"] for hunk in snapshot["hunks"]}
        groups = []
        for group_id, risk, needs_improvement, path in (
            ("low", "低リスク", False, "low.txt"),
            ("high", "要注意", False, "high.txt"),
            ("improve", "低リスク", True, "improve.txt"),
        ):
            groups.append(
                {
                    "id": group_id,
                    "title": group_id,
                    "summary": "summary",
                    "intent": "intent",
                    "impact": "impact",
                    "kind": "implementation",
                    "risk": risk,
                    "risk_reason": "reason",
                    "needs_improvement": needs_improvement,
                    "needs_improvement_reason": "mixed intent" if needs_improvement else "",
                    "hunk_ids": [hunk_id_by_path[path]],
                }
            )
        manifest_path = self.root / "ordered-manifest.json"
        manifest_path.write_text(
            json.dumps({"version": 1, "title": "Ordering", "groups": groups}),
            encoding="utf-8",
        )
        report = self.root / "ordered.html"

        # Act: 意図的に低リスク順で渡した group を生成する。
        result = self._run(
            "render",
            "--snapshot",
            str(snapshot_path),
            "--manifest",
            str(manifest_path),
            "--output",
            str(report),
            "--no-open",
        )

        # Assert: 要改善を先頭にし、その後はリスク順に並べる。
        self.assertEqual(0, result.returncode, result.stderr)
        data = self._read_report_data(report)
        self.assertEqual(
            ["improve", "high", "low"],
            [group["id"] for group in data["manifest"]["groups"]],
        )

    def test_render_encodes_untrusted_diff_and_manifest_text_as_data(self) -> None:
        # Arrange: script を閉じる payload を差分と人間入力 metadata の両方へ入れる。
        payload = "</script><script>globalThis.compromised = true</script>"
        (self.repo / "mixed.txt").write_text(f"base\n{payload}\n", encoding="utf-8")
        snapshot_path = self.root / "unsafe-snapshot.json"
        snapshot_result = self._run("snapshot", "--output", str(snapshot_path))
        self.assertEqual(0, snapshot_result.returncode, snapshot_result.stderr)
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        manifest_path = self._write_manifest(snapshot)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["groups"][0]["summary"] = payload
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        report = self.root / "safe.html"

        # Act: 信頼できない repository 内容を自己完結レポートへ生成する。
        result = self._run(
            "render",
            "--snapshot",
            str(snapshot_path),
            "--manifest",
            str(manifest_path),
            "--output",
            str(report),
            "--no-open",
        )

        # Assert: payload はデータとして保持し、実行可能な markup には展開しない。
        self.assertEqual(0, result.returncode, result.stderr)
        html = report.read_text(encoding="utf-8")
        self.assertNotIn(payload, html)
        data = self._read_report_data(report)
        self.assertEqual(payload, data["manifest"]["groups"][0]["summary"])
        self.assertIn(payload, data["snapshot"]["entries"][0]["raw_diff"])

    def test_verify_accepts_current_fingerprint_and_rejects_stale_fingerprint(self) -> None:
        # Arrange: 現在の fingerprint を取得し、公開 verify コマンドへ渡す。
        snapshot_path, snapshot = self._snapshot_with_one_change()

        # Act: 同じ差分と、worktree 変更後の差分をそれぞれ検証する。
        current = self._run("verify", "--fingerprint", snapshot["fingerprint"])
        (self.repo / "mixed.txt").write_text("base\nchanged again\n", encoding="utf-8")
        stale = self._run("verify", "--fingerprint", snapshot["fingerprint"])

        # Assert: 表示中の差分を指している間だけフィードバックを続行できる。
        self.assertEqual(0, current.returncode, current.stderr)
        self.assertNotEqual(0, stale.returncode)
        self.assertIn("stale", stale.stderr)

    def test_snapshot_defaults_to_a_fingerprint_directory_in_the_worktree_git_path(self) -> None:
        # Arrange: ローカル変更を 1 つ作り、worktree 対応の Git 保存先を解決する。
        (self.repo / "mixed.txt").write_text("base\nchanged\n", encoding="utf-8")
        git_path = Path(self._git("rev-parse", "--path-format=absolute", "--git-path", "explain-diff").stdout.strip())

        # Act: 出力先を明示せずに収集する。
        result = self._run("snapshot")

        # Assert: artifact は worktree 外の fingerprint 別ディレクトリへ置かれる。
        self.assertEqual(0, result.returncode, result.stderr)
        output = Path(result.stdout.strip())
        snapshot = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(git_path, output.parent.parent)
        self.assertEqual(snapshot["fingerprint"], output.parent.name)
        self.assertEqual("snapshot.json", output.name)

    def test_snapshot_rejects_a_repository_without_local_changes(self) -> None:
        # Arrange: setup 後の fixture repository は clean な状態にある。

        # Act: ローカル差分の snapshot を要求する。
        result = self._run("snapshot", "--output", str(self.root / "empty.json"))

        # Assert: 誤解を招く空のレビューは生成しない。
        self.assertNotEqual(0, result.returncode)
        self.assertIn("no local changes", result.stderr)
        self.assertFalse((self.root / "empty.json").exists())

    def test_report_template_exposes_lazy_review_and_feedback_controls(self) -> None:
        # Arrange & Act: skill に同梱された決定的な UI 契約を読み込む。
        template = TEMPLATE.read_text(encoding="utf-8")

        # Assert: レポートが全体像、グループ単位の確認、状態保存、フィードバックを提供する。
        for contract_marker in (
            'id="overview"',
            'id="diagram-list"',
            'id="group-list"',
            'id="detail-card"',
            'id="generate-feedback"',
            'id="copy-feedback"',
            "function renderOverview()",
            "function renderGlossary()",
            "function openInfluenceTarget(",
            "term_ids: link.term_ids ?? []",
            "Mermaid node link target not found:",
            'target?.closest(".file-diff-body")',
            "function highlightCode(",
            "Prism.highlight(",
            "function renderActiveGroup()",
            "localStorage.setItem(storageKey",
            'aria-live="polite"',
        ):
            self.assertIn(contract_marker, template)
        self.assertNotIn("__GROUP_ROWS__", template)
        self.assertNotIn("リスク分布", template)
        self.assertNotIn("function renderSwimlaneDiagram(", template)
        self.assertNotIn("function renderImpactMap(", template)
        self.assertNotIn("function applyGroupFilter(", template)
        self.assertNotIn('"impact-badge " + influence.level', template)
        self.assertNotIn('!text.startsWith("+++")', template)
        self.assertNotIn('!text.startsWith("---")', template)

    def test_report_template_keeps_navigation_diff_and_context_visible_together(self) -> None:
        # Arrange & Act: レビュー画面のレスポンシブなレイアウト契約を読み込む。
        template = TEMPLATE.read_text(encoding="utf-8")

        # Assert: デスクトップでは3領域を同時表示し、図と用語を同じcontext railで参照できる。
        for contract_marker in (
            'class="review-workspace"',
            'class="group-rail"',
            'class="review-main"',
            'class="context-rail"',
            'class="context-panel context-diagram"',
            'class="context-panel context-glossary"',
            "grid-template-columns: 240px minmax(0, 1fr) minmax(360px, 420px)",
            "function syncReviewContext(",
            "function focusGlossaryTerm(",
        ):
            self.assertIn(contract_marker, template)

    def test_report_template_groups_hunks_by_file_and_shows_them_without_collapsing(self) -> None:
        # Arrange & Act: 同じファイルに複数hunkがある場合の表示契約を読み込む。
        template = TEMPLATE.read_text(encoding="utf-8")

        # Assert: file単位のcardへhunkをまとめ、diffを初期状態から連続して読める。
        for contract_marker in (
            "function groupHunksByPath(",
            "function renderFileDiff(",
            ".file-diff {",
            ".file-diff-header {",
        ):
            self.assertIn(contract_marker, template)
        self.assertNotIn('element("details", "hunk")', template)

    def test_report_template_persists_file_collapse_and_reviewed_states(self) -> None:
        # Arrange & Act: file単位でレビューを進める状態管理契約を読み込む。
        template = TEMPLATE.read_text(encoding="utf-8")

        # Assert: fileは初期展開のまま任意に折りたため、確認状態もfeedbackまで保持する。
        for contract_marker in (
            "fileChecked: {}",
            "fileCollapsed: {}",
            'setAttribute("aria-expanded"',
            'checkbox.setAttribute("aria-label"',
            "state.fileChecked[fileKey]",
            "state.fileCollapsed[fileKey]",
            "uncheckedFiles",
        ):
            self.assertIn(contract_marker, template)

    def test_report_template_collapses_a_file_when_it_is_marked_reviewed(self) -> None:
        # Arrange & Act: file確認操作の状態遷移契約を読み込む。
        template = TEMPLATE.read_text(encoding="utf-8")

        # Assert: 確認済みを付けたときだけ、同じfileを即座に折りたたむ。
        self.assertIn("if (checkbox.checked) setFileCollapsed(true);", template)

    def test_snapshot_does_not_follow_an_untracked_symlink_outside_the_repository(self) -> None:
        # Arrange: レポートへ入れてはいけない外部内容を未追跡 symlink から参照する。
        secret = self.root / "outside-secret.txt"
        secret.write_text("DO_NOT_CAPTURE_THIS_CONTENT\n", encoding="utf-8")
        os.symlink(secret, self.repo / "outside-link")
        output = self.root / "symlink-snapshot.json"

        # Act: 公開 CLI からローカル差分を収集する。
        result = self._run("snapshot", "--output", str(output))

        # Assert: symlink の参照先を読まず、link 自体だけを snapshot に記録する。
        self.assertEqual(0, result.returncode, result.stderr)
        snapshot_text = output.read_text(encoding="utf-8")
        snapshot = json.loads(snapshot_text)
        link_entry = next(entry for entry in snapshot["entries"] if entry["path"] == "outside-link")
        self.assertNotIn("DO_NOT_CAPTURE_THIS_CONTENT", snapshot_text)
        self.assertEqual("symlink", link_entry["file_type"])
        self.assertIn(str(secret), link_entry["raw_diff"])

    def test_snapshot_counts_content_that_resembles_diff_file_headers(self) -> None:
        # Arrange: unified diff では +++/--- に見える実際の変更行を用意する。
        (self.repo / "mixed.txt").write_text("base\n--removed-looking\n", encoding="utf-8")
        self._git("add", "mixed.txt")
        (self.repo / "mixed.txt").write_text("base\n++added-looking\n", encoding="utf-8")
        output = self.root / "header-looking.json"

        # Act: ローカル差分から要約統計を収集する。
        result = self._run("snapshot", "--output", str(output))

        # Assert: file header に似た内容も追加・削除行として数える。
        self.assertEqual(0, result.returncode, result.stderr)
        stats = json.loads(output.read_text(encoding="utf-8"))["stats"]
        self.assertEqual(2, stats["additions"])
        self.assertEqual(1, stats["deletions"])

    def test_serve_defaults_to_loopback_with_an_ephemeral_port(self) -> None:
        # Arrange: 生成済みレポートを用意し、fake server で socket 境界を隔離する。
        report = self.root / "report.html"
        report.write_text(
            '<!doctype html><html data-explain-diff-report="1"><title>Report</title></html>',
            encoding="utf-8",
        )
        output = io.StringIO()

        # Act: hostを指定せず、fakeがCtrl-Cを再現するまでserverを動かす。
        with redirect_stdout(output):
            result = MODULE.serve_report(report, server_factory=FakeHttpServer)

        # Assert: remote interfaceへ公開せず、localhostだけで配信する。
        self.assertEqual(0, result)
        self.assertEqual(("127.0.0.1", 0), FakeHttpServer.created_address)
        self.assertNotIn("WARNING", output.getvalue())
        self.assertIn("127.0.0.1:43123/report.html", output.getvalue())

    def test_serve_cli_defaults_to_loopback(self) -> None:
        # Arrange & Act: hostを省略したserve commandを解析する。
        args = MODULE.build_parser().parse_args(["serve", "--report", "report.html"])

        # Assert: CLI入口もlocalhost以外へ暗黙に公開しない。
        self.assertEqual("127.0.0.1", args.host)

    def test_serve_hosts_one_report_on_an_explicit_remote_interface(self) -> None:
        # Arrange: 生成済みレポートを用意し、fake server で socket 境界を隔離する。
        report = self.root / "report.html"
        report.write_text(
            '<!doctype html><html data-explain-diff-report="1"><title>Report</title></html>',
            encoding="utf-8",
        )
        output = io.StringIO()

        # Act: fake が Ctrl-C を再現するまで foreground server を動かす。
        with redirect_stdout(output):
            result = MODULE.serve_report(
                report,
                host="0.0.0.0",
                port=0,
                server_factory=FakeHttpServer,
            )

        # Assert: 明示された全interface bind、port、警告、URL、終了処理を観測できる。
        self.assertEqual(0, result)
        self.assertEqual(("0.0.0.0", 0), FakeHttpServer.created_address)
        self.assertTrue(FakeHttpServer.served)
        self.assertTrue(FakeHttpServer.closed)
        self.assertIn("all configured interfaces", output.getvalue())
        self.assertIn("43123/report.html", output.getvalue())

    def test_serve_rejects_a_file_that_is_not_an_explain_diff_report(self) -> None:
        # Arrange: serve に任意のローカル HTML を指定する。
        arbitrary = self.root / "arbitrary.html"
        arbitrary.write_text("<!doctype html><title>Not a report</title>", encoding="utf-8")

        # Act & Assert: listen socket を作る前に検証で停止する。
        with self.assertRaisesRegex(ValueError, "explain-diff report"):
            MODULE.serve_report(arbitrary, server_factory=FakeHttpServer)
        self.assertIsNone(FakeHttpServer.created_address)

    def test_serve_warns_when_an_explicit_host_is_not_loopback(self) -> None:
        # Arrange: 全 interface の既定値ではなく Tailscale 範囲の address を使う。
        report = self.root / "report.html"
        report.write_text(
            '<!doctype html><html data-explain-diff-report="1"></html>',
            encoding="utf-8",
        )
        output = io.StringIO()

        # Act: 隔離した socket 境界から配信する。
        with redirect_stdout(output):
            MODULE.serve_report(
                report,
                host="100.64.0.10",
                server_factory=FakeHttpServer,
            )

        # Assert: remote 到達可能な明示 bind でも差分公開の警告を表示する。
        self.assertIn("WARNING", output.getvalue())
        self.assertIn("full local diff", output.getvalue())


if __name__ == "__main__":
    unittest.main()
