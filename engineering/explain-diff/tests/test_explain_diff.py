from __future__ import annotations

import json
import base64
from contextlib import redirect_stderr
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
            "version": 2,
            "title": "Example local diff",
            "context": "The current behavior cannot express the intended result.",
            "outcome": "The intended result is now visible to the user.",
            "groups": [
                {
                    "id": "behavior",
                    "title": "Behavior change",
                    "before": "The example only contains its base behavior.",
                    "after": "The example also contains the changed behavior.",
                    "why": "This is the smallest change that produces the intended result.",
                    "review_focus": "Confirm that the added behavior matches the intended result.",
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

    def test_render_rejects_a_node_link_without_a_navigation_group(self) -> None:
        # Arrange: hunkだけを参照し、移動先groupを持たないnode linkを定義する。
        snapshot_path, snapshot = self._snapshot_with_one_change()
        manifest_path = self._write_manifest(snapshot)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["diagrams"] = [{
            "id": "flow",
            "title": "処理flow",
            "description": "移動先groupのないnode link。",
            "format": "mermaid",
            "diagram_kind": "flowchart",
            "source": "flowchart TB\n  input --> output",
            "node_links": [{
                "node_id": "output",
                "group_ids": [],
                "hunk_ids": [snapshot["hunks"][0]["id"]],
                "term_ids": [],
            }],
        }]
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        # Act: public render commandでnavigation contractを検証する。
        result = self._run("render", "--snapshot", str(snapshot_path), "--manifest",
                           str(manifest_path), "--output",
                           str(self.root / "group-less-link.html"), "--no-open")

        # Assert: 操作可能に見えて無反応になるnodeをreportへ出さない。
        self.assertNotEqual(0, result.returncode)
        self.assertIn("node link must include a group id", result.stderr)
        self.assertFalse((self.root / "group-less-link.html").exists())

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

    def test_render_preserves_the_manifest_story_order(self) -> None:
        # Arrange: 現在の hunk を 3 つ作り、因果順に group を定義する。
        for path in ("contract.txt", "implementation.txt", "test.txt"):
            (self.repo / path).write_text(f"{path}\n", encoding="utf-8")
        snapshot_path = self.root / "ordered-snapshot.json"
        snapshot_result = self._run("snapshot", "--output", str(snapshot_path))
        self.assertEqual(0, snapshot_result.returncode, snapshot_result.stderr)
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        hunk_id_by_path = {hunk["path"]: hunk["id"] for hunk in snapshot["hunks"]}
        groups = []
        for group_id, path in (
            ("contract", "contract.txt"),
            ("implementation", "implementation.txt"),
            ("test", "test.txt"),
        ):
            groups.append(
                {
                    "id": group_id,
                    "title": group_id,
                    "before": "before",
                    "after": "after",
                    "why": "why",
                    "review_focus": "review focus",
                    "hunk_ids": [hunk_id_by_path[path]],
                }
            )
        manifest_path = self.root / "ordered-manifest.json"
        manifest_path.write_text(
            json.dumps({
                "version": 2,
                "title": "Ordering",
                "context": "context",
                "outcome": "outcome",
                "groups": groups,
            }),
            encoding="utf-8",
        )
        report = self.root / "ordered.html"

        # Act: contract → implementation → test の順で渡した group を生成する。
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

        # Assert: 説明者が選んだ因果順を並べ替えずに保つ。
        self.assertEqual(0, result.returncode, result.stderr)
        data = self._read_report_data(report)
        self.assertEqual(
            ["contract", "implementation", "test"],
            [group["id"] for group in data["manifest"]["groups"]],
        )

    def test_render_rejects_a_group_dependency_that_points_backwards(self) -> None:
        # Arrange: 入口から依存先へ並べた順序に反して、後続groupから入口を参照する。
        (self.repo / "entry.txt").write_text("entry\n", encoding="utf-8")
        (self.repo / "mixed.txt").write_text("base\nbehavior\n", encoding="utf-8")
        snapshot_path = self.root / "outside-in-snapshot.json"
        snapshot_result = self._run("snapshot", "--output", str(snapshot_path))
        self.assertEqual(0, snapshot_result.returncode, snapshot_result.stderr)
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        hunk_id_by_path = {hunk["path"]: hunk["id"] for hunk in snapshot["hunks"]}
        groups = [
            {
                "id": "entry", "title": "利用者から見える入口", "before": "before",
                "after": "after", "why": "why", "review_focus": "review focus",
                "hunk_ids": [hunk_id_by_path["entry.txt"]],
            },
            {
                "id": "behavior", "title": "入口を成立させる判断", "before": "before",
                "after": "after", "why": "why", "review_focus": "review focus",
                "depends_on": ["entry"], "hunk_ids": [hunk_id_by_path["mixed.txt"]],
            },
        ]
        manifest_path = self.root / "backwards-dependency.json"
        manifest_path.write_text(json.dumps({
            "version": 2, "title": "Outside-in ordering", "context": "context",
            "outcome": "outcome", "groups": groups,
        }), encoding="utf-8")

        # Act: public render commandから逆向きの理解経路を検証する。
        result = self._run("render", "--snapshot", str(snapshot_path), "--manifest",
                           str(manifest_path), "--output",
                           str(self.root / "backwards-dependency.html"), "--no-open")

        # Assert: groupを入口から依存先へ読めないmanifestはartifactにしない。
        self.assertNotEqual(0, result.returncode)
        self.assertIn("must point to a later group", result.stderr)

    def test_render_rejects_a_duplicate_group_dependency(self) -> None:
        # Arrange: 同じ依存先を二重に示し、理解経路が重複するmanifestを作る。
        (self.repo / "entry.txt").write_text("entry\n", encoding="utf-8")
        (self.repo / "mixed.txt").write_text("base\nbehavior\n", encoding="utf-8")
        snapshot_path = self.root / "duplicate-dependency-snapshot.json"
        snapshot_result = self._run("snapshot", "--output", str(snapshot_path))
        self.assertEqual(0, snapshot_result.returncode, snapshot_result.stderr)
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        hunk_id_by_path = {hunk["path"]: hunk["id"] for hunk in snapshot["hunks"]}
        manifest_path = self.root / "duplicate-dependency-manifest.json"
        manifest_path.write_text(json.dumps({
            "version": 2, "title": "Duplicate dependency", "context": "context",
            "outcome": "outcome", "groups": [
                {
                    "id": "entry", "title": "利用者から見える入口", "before": "before",
                    "after": "after", "why": "why", "review_focus": "review focus",
                    "depends_on": ["behavior", "behavior"],
                    "hunk_ids": [hunk_id_by_path["entry.txt"]],
                },
                {
                    "id": "behavior", "title": "入口を成立させる判断", "before": "before",
                    "after": "after", "why": "why", "review_focus": "review focus",
                    "hunk_ids": [hunk_id_by_path["mixed.txt"]],
                },
            ],
        }), encoding="utf-8")

        # Act: public render commandから重複した理解経路を検証する。
        result = self._run("render", "--snapshot", str(snapshot_path), "--manifest",
                           str(manifest_path), "--output",
                           str(self.root / "duplicate-dependency.html"), "--no-open")

        # Assert: 同じedgeを複数表示するmanifestはartifactにしない。
        self.assertNotEqual(0, result.returncode)
        self.assertIn("duplicate dependency group", result.stderr)

    def test_render_preserves_an_outside_in_group_path(self) -> None:
        # Arrange: 利用者側の入口から内部の依存先へ進む2つのgroupを作る。
        (self.repo / "entry.txt").write_text("entry\n", encoding="utf-8")
        (self.repo / "mixed.txt").write_text("base\nbehavior\n", encoding="utf-8")
        snapshot_path = self.root / "outside-in-snapshot.json"
        snapshot_result = self._run("snapshot", "--output", str(snapshot_path))
        self.assertEqual(0, snapshot_result.returncode, snapshot_result.stderr)
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        hunk_id_by_path = {hunk["path"]: hunk["id"] for hunk in snapshot["hunks"]}
        groups = [
            {
                "id": "entry", "title": "利用者から見える入口", "before": "before",
                "after": "after", "why": "why", "review_focus": "review focus",
                "depends_on": ["behavior"], "hunk_ids": [hunk_id_by_path["entry.txt"]],
            },
            {
                "id": "behavior", "title": "入口を成立させる判断", "before": "before",
                "after": "after", "why": "why", "review_focus": "review focus",
                "hunk_ids": [hunk_id_by_path["mixed.txt"]],
            },
        ]
        manifest_path = self.root / "outside-in-manifest.json"
        manifest_path.write_text(json.dumps({
            "version": 2, "title": "Outside-in ordering", "context": "context",
            "outcome": "outcome", "groups": groups,
        }), encoding="utf-8")
        report = self.root / "outside-in.html"

        # Act: 入口groupが後続の依存先を指すreportを生成する。
        result = self._run("render", "--snapshot", str(snapshot_path), "--manifest",
                           str(manifest_path), "--output", str(report), "--no-open")

        # Assert: rendererが理解経路と全groupの初期表示を提供する。
        self.assertEqual(0, result.returncode, result.stderr)
        data = self._read_report_data(report)
        self.assertEqual(["behavior"], data["manifest"]["groups"][0]["depends_on"])
        html = report.read_text(encoding="utf-8")
        self.assertIn('class="reading-path"', html)
        self.assertIn('"group-dependencies"', html)
        self.assertIn("dependedGroupIds.has(group.id)", html)
        self.assertIn("function renderAllGroups()", html)
        self.assertIn("group-section-${group.id}", html)

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
        manifest["groups"][0]["after"] = payload
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
        self.assertEqual(payload, data["manifest"]["groups"][0]["after"])
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

        # Assert: レポートが変更の物語、根拠、確認状態、フィードバックを提供する。
        for contract_marker in (
            'id="story-section"',
            'id="story-context"',
            'id="story-outcome"',
            'id="system-overview"',
            'id="overview"',
            'id="diagram-list"',
            'id="changed-files"',
            "function renderChangedFiles()",
            'id="group-list"',
            'id="detail-card"',
            'id="generate-feedback"',
            'id="copy-feedback"',
            "function renderOverview()",
            "function renderStory()",
            "function renderGlossary()",
            "function openInfluenceTarget(",
            "term_ids: link.term_ids ?? []",
            "Mermaid node link target not found:",
            'target?.closest(".file-diff-body")',
            "function highlightCode(",
            "Prism.highlight(",
            "function renderAllGroups()",
            "localStorage.setItem(storageKey",
            'aria-live="polite"',
        ):
            self.assertIn(contract_marker, template)
        self.assertNotIn("__GROUP_ROWS__", template)
        self.assertNotIn("リスク分布", template)
        self.assertNotIn("riskClass(", template)
        self.assertNotIn("function renderSwimlaneDiagram(", template)
        self.assertNotIn("function renderImpactMap(", template)
        self.assertNotIn("function applyGroupFilter(", template)
        self.assertNotIn('"impact-badge " + influence.level', template)
        self.assertNotIn('!text.startsWith("+++")', template)
        self.assertNotIn('!text.startsWith("---")', template)

    def test_report_template_links_mermaid_nodes_with_a_diagram_specific_id_prefix(self) -> None:
        # Arrange & Act: Mermaidが図固有prefix付きで生成するnodeとmanifestのnode_idを結ぶtemplateを読む。
        template = TEMPLATE.read_text(encoding="utf-8")

        # Assert: `mermaid-<diagram>-flowchart-api-0` のような実DOM IDでもapiを解決する。
        self.assertIn('output.querySelectorAll(".node[id]")', template)
        self.assertIn('node.id.includes(`flowchart-${link.node_id}-`)', template)

    def test_report_template_keeps_navigation_diff_and_context_visible_together(self) -> None:
        # Arrange & Act: レビュー画面のレスポンシブなレイアウト契約を読み込む。
        template = TEMPLATE.read_text(encoding="utf-8")

        # Assert: デスクトップでは説明前に構造と変更範囲を俯瞰し、レビュー中も用語を参照できる。
        for contract_marker in (
            "system-overview without-architecture",
            'class="architecture-panel"',
            'class="changed-files-panel"',
            'class="review-workspace"',
            'class="group-rail"',
            'class="review-main"',
            'class="context-rail"',
            'class="context-panel context-glossary"',
            "grid-template-columns: minmax(0, 3fr) minmax(320px, 2fr)",
            "function syncReviewContext(",
            "function focusGlossaryTerm(",
            'classList.remove("without-architecture")',
        ):
            self.assertIn(contract_marker, template)

    def test_report_template_tracks_the_active_group_while_reading_all_sections(self) -> None:
        # Arrange & Act: 全groupを連続して読むreport templateを読み込む。
        template = TEMPLATE.read_text(encoding="utf-8")

        # Assert: 本文の読書位置がrailとMermaidのactive contextへ反映される。
        self.assertIn("function syncActiveGroupFromScroll()", template)
        self.assertIn('window.addEventListener("scroll", scheduleActiveGroupSync', template)
        self.assertIn("syncReviewContext(groupId)", template)
        self.assertIn("document.documentElement.scrollHeight - 1", template)
        self.assertIn("document.documentElement.scrollHeight > window.innerHeight + 1", template)
        self.assertIn("function keepActiveGroupVisible()", template)

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

    def test_cli_rejects_the_removed_serve_command(self) -> None:
        # Arrange: 配信責務を分離した後の CLI contract を使う。
        parser = MODULE.build_parser()

        # Act & Assert: explain-diff 自身には server command を残さない。
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                parser.parse_args(["serve", "--report", "report.html"])


if __name__ == "__main__":
    unittest.main()
