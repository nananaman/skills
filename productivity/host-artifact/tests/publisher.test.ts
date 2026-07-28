import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtemp, mkdir, readFile, readdir, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { promisify } from "node:util";
import { hostArtifact, removeArtifact } from "../src/publisher.js";

const execFileAsync = promisify(execFile);

test("file input is copied to a new capability directory", async () => {
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
  assert.equal(hosted.id, `local-${"a".repeat(32)}`);
  assert.equal(hosted.relativePath, "report.html");
  assert.equal(await readFile(path.join(root, hosted.id, "report.html"), "utf8"), "<h1>snapshot</h1>");
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
  const id = `local-${"e".repeat(32)}`;
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
  assert.equal(await readFile(path.join(root, a.id, a.relativePath), "utf8"), "first");
  assert.equal(await readFile(path.join(root, b.id, b.relativePath), "utf8"), "second");
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
