import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtemp, mkdir, readFile, readdir, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { promisify } from "node:util";
import { hostArtifact, removeArtifact, updateArtifact } from "../src/publisher.js";

const execFileAsync = promisify(execFile);

test("HTML file input receives live reload while the source remains unchanged", async () => {
  // Arrange
  const base = await mkdtemp(path.join(tmpdir(), "host-artifact-"));
  const source = path.join(base, "report.html");
  const root = path.join(base, "public");
  await mkdir(root);
  await writeFile(source, "<h1>snapshot</h1>");

  // Act
  const hosted = await hostArtifact(source, { root, idGenerator: () => "a".repeat(32) });
  await writeFile(source, "changed");

  // Assert
  assert.equal(hosted.id, `local-live-${"a".repeat(32)}`);
  assert.equal(hosted.relativePath, "report.html");
  assert.match(await readFile(path.join(root, hosted.id, "report.html"), "utf8"), /data-host-artifact-live-reload/);
  assert.equal(await readFile(source, "utf8"), "changed");
});

test("HTML file input preserves exact content when live reload is disabled", async () => {
  // Arrange
  const base = await mkdtemp(path.join(tmpdir(), "host-artifact-"));
  const source = path.join(base, "report.html");
  const root = path.join(base, "public");
  await mkdir(root);
  await writeFile(source, "<h1>snapshot</h1>");

  // Act
  const hosted = await hostArtifact(source, {
    root,
    idGenerator: () => "a".repeat(32),
    liveReload: false,
  });

  // Assert
  assert.equal(hosted.id, `local-${"a".repeat(32)}`);
  assert.equal(await readFile(path.join(root, hosted.id, "report.html"), "utf8"), "<h1>snapshot</h1>");
});

test("single-file update preserves the capability path and replaces its content", async () => {
  // Arrange
  const base = await mkdtemp(path.join(tmpdir(), "host-artifact-"));
  const source = path.join(base, "report.html");
  const root = path.join(base, "public");
  await mkdir(root);
  await writeFile(source, "before");
  const hosted = await hostArtifact(source, { root, idGenerator: () => "4".repeat(32) });
  await writeFile(source, "after");

  // Act
  const updated = await updateArtifact(hosted.id, source, { root });

  // Assert
  assert.deepEqual(updated, hosted);
  assert.match(await readFile(path.join(root, hosted.id, hosted.relativePath), "utf8"), /after.*data-host-artifact-live-reload/s);
});

test("update rejects an invalid artifact identifier", async () => {
  // Arrange
  const base = await mkdtemp(path.join(tmpdir(), "host-artifact-"));
  const source = path.join(base, "report.html");
  const root = path.join(base, "public");
  await mkdir(root);
  await writeFile(source, "after");

  // Act & Assert
  await assert.rejects(updateArtifact("../outside", source, { root }), /artifact id/i);
});

test("update rejects a symlink source", async () => {
  // Arrange
  const base = await mkdtemp(path.join(tmpdir(), "host-artifact-"));
  const source = path.join(base, "report.html");
  const root = path.join(base, "public");
  await mkdir(root);
  await symlink("/etc/passwd", source);

  // Act & Assert
  await assert.rejects(updateArtifact(`local-${"4".repeat(32)}`, source, { root }), /symlink/i);
});

test("update rejects a dotfile source", async () => {
  // Arrange
  const base = await mkdtemp(path.join(tmpdir(), "host-artifact-"));
  const source = path.join(base, ".report.html");
  const root = path.join(base, "public");
  await mkdir(root);
  await writeFile(source, "after");

  // Act & Assert
  await assert.rejects(updateArtifact(`local-${"4".repeat(32)}`, source, { root }), /dotfile/i);
});

test("update rejects a directory source", async () => {
  // Arrange
  const base = await mkdtemp(path.join(tmpdir(), "host-artifact-"));
  const source = path.join(base, "site");
  const root = path.join(base, "public");
  await mkdir(root);
  await mkdir(source);
  await writeFile(path.join(source, "index.html"), "after");

  // Act & Assert
  await assert.rejects(updateArtifact(`local-${"4".repeat(32)}`, source, { root }), /regular file/i);
});

test("update rejects a filename mismatch and preserves the established content", async () => {
  // Arrange
  const base = await mkdtemp(path.join(tmpdir(), "host-artifact-"));
  const original = path.join(base, "report.html");
  const replacement = path.join(base, "other.html");
  const root = path.join(base, "public");
  await mkdir(root);
  await writeFile(original, "before");
  await writeFile(replacement, "after");
  const hosted = await hostArtifact(original, { root, idGenerator: () => "5".repeat(32) });
  const established = await readFile(path.join(root, hosted.id, hosted.relativePath), "utf8");

  // Act & Assert
  await assert.rejects(updateArtifact(hosted.id, replacement, { root }), /filename/i);
  assert.equal(await readFile(path.join(root, hosted.id, hosted.relativePath), "utf8"), established);
});

test("update rejects a directory artifact and preserves its contents", async () => {
  // Arrange
  const base = await mkdtemp(path.join(tmpdir(), "host-artifact-"));
  const source = path.join(base, "site");
  const replacement = path.join(base, "index.html");
  const root = path.join(base, "public");
  await mkdir(root);
  await mkdir(path.join(source, "assets"), { recursive: true });
  await writeFile(path.join(source, "index.html"), "before");
  await writeFile(path.join(source, "assets", "app.js"), "app");
  await writeFile(replacement, "after");
  const hosted = await hostArtifact(source, { root, idGenerator: () => "6".repeat(32) });

  // Act & Assert
  await assert.rejects(updateArtifact(hosted.id, replacement, { root }), /single-file/i);
  assert.equal(await readFile(path.join(root, hosted.id, "index.html"), "utf8"), "before");
});

test("directory input is copied without changing its layout", async () => {
  // Arrange
  const base = await mkdtemp(path.join(tmpdir(), "host-artifact-"));
  const source = path.join(base, "site");
  const root = path.join(base, "public");
  await mkdir(root);
  await mkdir(path.join(source, "assets"), { recursive: true });
  await writeFile(path.join(source, "index.html"), "index");
  await writeFile(path.join(source, "assets", "app.js"), "app");

  // Act
  const hosted = await hostArtifact(source, { root, idGenerator: () => "b".repeat(32) });

  // Assert
  assert.equal(hosted.relativePath, "index.html");
  assert.equal(await readFile(path.join(root, hosted.id, "assets", "app.js"), "utf8"), "app");
});

test("directory without a regular top-level index is rejected without publishing", async () => {
  // Arrange
  const base = await mkdtemp(path.join(tmpdir(), "host-artifact-"));
  const source = path.join(base, "site");
  const root = path.join(base, "public");
  await mkdir(root);
  await mkdir(source);
  await writeFile(path.join(source, "page.html"), "page");

  // Act & Assert
  await assert.rejects(hostArtifact(source, { root }), /index\.html/i);
  assert.deepEqual(await readdir(root), []);
});

test("input containing a symlink is rejected", async () => {
  // Arrange
  const base = await mkdtemp(path.join(tmpdir(), "host-artifact-"));
  const source = path.join(base, "site");
  await mkdir(source);
  await symlink("/etc/passwd", path.join(source, "escape"));

  // Act & Assert
  await assert.rejects(hostArtifact(source, { root: path.join(base, "public") }), /symlink/i);
});

test("input containing a dotfile is rejected", async () => {
  // Arrange
  const base = await mkdtemp(path.join(tmpdir(), "host-artifact-"));
  const source = path.join(base, "site");
  await mkdir(source);
  await writeFile(path.join(source, ".secret"), "secret");

  // Act & Assert
  await assert.rejects(hostArtifact(source, { root: path.join(base, "public") }), /dotfile/i);
});

test("directory containing a special file is rejected", async () => {
  // Arrange
  const base = await mkdtemp(path.join(tmpdir(), "host-artifact-"));
  const source = path.join(base, "site");
  await mkdir(source);
  await writeFile(path.join(source, "index.html"), "index");
  await execFileAsync("/usr/bin/mkfifo", [path.join(source, "stream")]);

  // Act & Assert
  await assert.rejects(hostArtifact(source, { root: path.join(base, "public") }), /special file/i);
});

test("remove accepts only an issued artifact identifier", async () => {
  // Arrange
  const base = await mkdtemp(path.join(tmpdir(), "host-artifact-"));
  const root = path.join(base, "public");
  await mkdir(root);

  // Act & Assert
  await assert.rejects(removeArtifact("../outside", { root }), /artifact id/i);
});

test("existing artifact identifier is never overwritten", async () => {
  // Arrange
  const base = await mkdtemp(path.join(tmpdir(), "host-artifact-"));
  const root = path.join(base, "public");
  const id = `local-live-${"e".repeat(32)}`;
  const source = path.join(base, "report.html");
  await mkdir(path.join(root, id), { recursive: true });
  await writeFile(path.join(root, id, "existing.html"), "existing");
  await writeFile(source, "new");

  // Act & Assert
  await assert.rejects(hostArtifact(source, { root, idGenerator: () => "e".repeat(32) }));
  assert.equal(await readFile(path.join(root, id, "existing.html"), "utf8"), "existing");
});

test("concurrent hosts with distinct generated identifiers do not collide", async () => {
  // Arrange
  const base = await mkdtemp(path.join(tmpdir(), "host-artifact-"));
  const root = path.join(base, "public");
  const first = path.join(base, "first.html");
  const second = path.join(base, "second.html");
  await mkdir(root);
  await writeFile(first, "first");
  await writeFile(second, "second");

  // Act
  const [a, b] = await Promise.all([
    hostArtifact(first, { root, idGenerator: () => "1".repeat(32) }),
    hostArtifact(second, { root, idGenerator: () => "2".repeat(32), scope: "tailscale" }),
  ]);

  // Assert
  assert.notEqual(a.id, b.id);
  assert.match(await readFile(path.join(root, a.id, a.relativePath), "utf8"), /^first.*data-host-artifact-live-reload/s);
  assert.match(await readFile(path.join(root, b.id, b.relativePath), "utf8"), /^second.*data-host-artifact-live-reload/s);
});

test("symlinked publish root rejects host without writing outside", async () => {
  // Arrange
  const base = await mkdtemp(path.join(tmpdir(), "host-artifact-"));
  const outside = path.join(base, "outside");
  const root = path.join(base, "public");
  const source = path.join(base, "report.html");
  await mkdir(outside);
  await symlink(outside, root);
  await writeFile(source, "content");

  // Act & Assert
  await assert.rejects(hostArtifact(source, { root }), /publish root/i);
  assert.deepEqual(await readdir(outside), []);
});

test("symlinked publish root rejects remove without deleting outside", async () => {
  // Arrange
  const base = await mkdtemp(path.join(tmpdir(), "host-artifact-"));
  const outside = path.join(base, "outside");
  const root = path.join(base, "public");
  const id = `local-${"3".repeat(32)}`;
  await mkdir(path.join(outside, id), { recursive: true });
  await writeFile(path.join(outside, id, "index.html"), "keep");
  await symlink(outside, root);

  // Act & Assert
  await assert.rejects(removeArtifact(id, { root }), /publish root/i);
  assert.equal(await readFile(path.join(outside, id, "index.html"), "utf8"), "keep");
});
