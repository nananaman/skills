import assert from "node:assert/strict";
import { execFile, spawn } from "node:child_process";
import { once } from "node:events";
import { mkdtemp, mkdir, readFile, readdir, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { promisify } from "node:util";
import { publishArtifact, removeArtifact } from "../src/publisher.js";

const workspace = "nananaman-skills~0123456789ab";
const execFileAsync = promisify(execFile);

async function createCrashedShlock(lock: string): Promise<void> {
  await mkdir(path.dirname(lock), { recursive: true });
  const owner = spawn("/bin/sleep", ["10"]);
  assert(owner.pid);
  await execFileAsync("/usr/bin/shlock", ["-p", String(owner.pid), "-f", lock]);
  owner.kill();
  await once(owner, "exit");
}

test("同じ workspace と name への publish は immutable revision を追加して current を切り替える", async () => {
  // Arrange: 同じ論理成果物へ二つの完成版を publish する。
  const base = await mkdtemp(path.join(tmpdir(), "host-artifact-"));
  const root = path.join(base, "public");
  const source = path.join(base, "report.html");
  await mkdir(root);
  await writeFile(source, "first");
  const revisions = ["r-" + "1".repeat(32), "r-" + "2".repeat(32)];

  // Act
  const first = await publishArtifact(source, { root, workspace, name: "report", revisionGenerator: () => revisions.shift()! });
  await writeFile(source, "second");
  const second = await publishArtifact(source, { root, workspace, name: "report", revisionGenerator: () => revisions.shift()! });

  // Assert: URL identity は安定し、revision と current だけが進む。
  assert.equal(first.route, `/a/${workspace}/report/`);
  assert.equal(second.route, first.route);
  assert.notEqual(first.revision, second.revision);
  const artifactRoot = path.join(root, "v2", "workspaces", workspace, "artifacts", "report");
  assert.deepEqual((await readdir(path.join(artifactRoot, "revisions"))).sort(), [first.revision, second.revision]);
  assert.equal(JSON.parse(await readFile(path.join(artifactRoot, "current.json"), "utf8")).revision, second.revision);
  assert.match(await readFile(path.join(artifactRoot, "revisions", second.revision, "report.html"), "utf8"), new RegExp(`data-host-artifact-version="${second.revision}"`));
  assert.equal(await readFile(source, "utf8"), "second");
});

test("remove は論理成果物の全 revision を削除する", async () => {
  // Arrange
  const base = await mkdtemp(path.join(tmpdir(), "host-artifact-"));
  const root = path.join(base, "public");
  const source = path.join(base, "image.png");
  await mkdir(root);
  await writeFile(source, "png");
  await publishArtifact(source, { root, workspace, name: "image", revisionGenerator: () => "r-" + "3".repeat(32) });

  // Act
  await removeArtifact({ root, workspace, name: "image" });

  // Assert
  await assert.rejects(readdir(path.join(root, "v2", "workspaces", workspace, "artifacts", "image")));
});

test("unsupported file input is rejected before a revision becomes visible", async () => {
  // Arrange
  const base = await mkdtemp(path.join(tmpdir(), "host-artifact-"));
  const root = path.join(base, "public");
  const source = path.join(base, "notes.txt");
  await mkdir(root);
  await writeFile(source, "text");

  // Act & Assert
  await assert.rejects(publishArtifact(source, { root, workspace, name: "notes" }), /supported browser artifact/i);
  assert.deepEqual(await readdir(root), []);
});

test("route verification failure restores the previously established current revision", async () => {
  // Arrange: 既存 revision を確立してから、次 revision の route 検証を失敗させる。
  const base = await mkdtemp(path.join(tmpdir(), "host-artifact-"));
  const root = path.join(base, "public"); const source = path.join(base, "report.html");
  await mkdir(root); await writeFile(source, "stable");
  const stable = await publishArtifact(source, { root, workspace, name: "report", revisionGenerator: () => "r-" + "6".repeat(32) });
  await writeFile(source, "unreachable");

  // Act & Assert: failure 後も読者が参照する current は旧 revision のまま。
  await assert.rejects(publishArtifact(source, { root, workspace, name: "report", revisionGenerator: () => "r-" + "7".repeat(32), verify: async () => { throw new Error("route mismatch"); } }), /route mismatch/);
  const current = JSON.parse(await readFile(path.join(root, "v2", "workspaces", workspace, "artifacts", "report", "current.json"), "utf8"));
  assert.equal(current.revision, stable.revision);
});

test("symlinked managed ancestor rejects publish without writing outside the root", async () => {
  // Arrange: attacker-controlled v2 directory redirects the managed namespace.
  const base = await mkdtemp(path.join(tmpdir(), "host-artifact-"));
  const root = path.join(base, "public"); const outside = path.join(base, "outside"); const source = path.join(base, "report.html");
  await mkdir(root); await mkdir(outside); await writeFile(path.join(outside, "sentinel"), "keep");
  await symlink(outside, path.join(root, "v2")); await writeFile(source, "content");

  // Act & Assert: no managed directory or revision is created through the link.
  await assert.rejects(publishArtifact(source, { root, workspace, name: "report" }), /managed directory|symlink/i);
  assert.deepEqual(await readdir(outside), ["sentinel"]);
  assert.equal(await readFile(path.join(outside, "sentinel"), "utf8"), "keep");
});

test("verification failure reports primary and every recovery failure without deleting the established revision", async () => {
  // Arrange
  const base = await mkdtemp(path.join(tmpdir(), "host-artifact-")); const root = path.join(base, "public"); const source = path.join(base, "report.html");
  await mkdir(root); await writeFile(source, "stable");
  const stable = await publishArtifact(source, { root, workspace, name: "report", revisionGenerator: () => `r-${"a".repeat(32)}` });
  await writeFile(source, "candidate");

  // Act
  const failure = await publishArtifact(source, {
    root, workspace, name: "report", revisionGenerator: () => `r-${"b".repeat(32)}`,
    verify: async () => { throw new Error("primary verification failed"); },
    recovery: {
      removeStaging: async () => { throw new Error("staging cleanup failed"); },
      removeDestination: async () => { throw new Error("destination cleanup failed"); },
    },
  }).then(() => undefined, (error: unknown) => error as Error);

  // Assert: primary cause remains first and independent recovery failures are all visible.
  assert(failure);
  assert.match(failure.message, /primary verification failed.*staging cleanup failed.*destination cleanup failed/s);
  assert.equal((failure as Error & { cause?: unknown }).cause instanceof Error && ((failure as Error & { cause?: Error }).cause?.message), "primary verification failed");
  const artifactRoot = path.join(root, "v2", "workspaces", workspace, "artifacts", "report");
  assert.equal(JSON.parse(await readFile(path.join(artifactRoot, "current.json"), "utf8")).revision, stable.revision);
  assert.equal((await readdir(path.join(artifactRoot, "revisions"))).includes(stable.revision), true);
});

test("temporary current write failure removes the unreachable destination and preserves established current", async () => {
  // Arrange: immutable destination の作成後、current metadata の書込みだけを失敗させる。
  const base = await mkdtemp(path.join(tmpdir(), "host-artifact-")); const root = path.join(base, "public"); const source = path.join(base, "report.html");
  await mkdir(root); await writeFile(source, "stable");
  const stable = await publishArtifact(source, { root, workspace, name: "report", revisionGenerator: () => `r-${"c".repeat(32)}` });
  await writeFile(source, "candidate");

  // Act
  await assert.rejects(publishArtifact(source, {
    root, workspace, name: "report", revisionGenerator: () => `r-${"d".repeat(32)}`,
    commit: { writeTemporaryCurrent: async () => { throw new Error("current write failed"); } },
  }), /current write failed/);

  // Assert
  const artifactRoot = path.join(root, "v2", "workspaces", workspace, "artifacts", "report");
  assert.equal(JSON.parse(await readFile(path.join(artifactRoot, "current.json"), "utf8")).revision, stable.revision);
  assert.deepEqual(await readdir(path.join(artifactRoot, "revisions")), [stable.revision]);
  assert.equal((await readdir(artifactRoot)).some((entry) => entry.startsWith(".current-")), false);
});

test("temporary current rename failure removes temporary metadata and unreachable destination", async () => {
  // Arrange: temporary metadata は完成するが current への切替だけを失敗させる。
  const base = await mkdtemp(path.join(tmpdir(), "host-artifact-")); const root = path.join(base, "public"); const source = path.join(base, "report.html");
  await mkdir(root); await writeFile(source, "stable");
  const stable = await publishArtifact(source, { root, workspace, name: "report", revisionGenerator: () => `r-${"e".repeat(32)}` });

  // Act
  await assert.rejects(publishArtifact(source, {
    root, workspace, name: "report", revisionGenerator: () => `r-${"f".repeat(32)}`,
    commit: { switchCurrent: async () => { throw new Error("current rename failed"); } },
  }), /current rename failed/);

  // Assert
  const artifactRoot = path.join(root, "v2", "workspaces", workspace, "artifacts", "report");
  assert.equal(JSON.parse(await readFile(path.join(artifactRoot, "current.json"), "utf8")).revision, stable.revision);
  assert.deepEqual(await readdir(path.join(artifactRoot, "revisions")), [stable.revision]);
  assert.equal((await readdir(artifactRoot)).some((entry) => entry.startsWith(".current-")), false);
});

test("publish recovers a stale lock owned by a dead process", async () => {
  // Arrange
  const base = await mkdtemp(path.join(tmpdir(), "host-artifact-")); const root = path.join(base, "public"); const source = path.join(base, "report.html");
  const lock = path.join(root, "v2", "workspaces", workspace, "artifacts", "report.lock");
  await createCrashedShlock(lock); await writeFile(source, "content");

  // Act
  const result = await publishArtifact(source, { root, workspace, name: "report", revisionGenerator: () => `r-${"1".repeat(32)}` });

  // Assert
  assert.equal(result.name, "report");
});

test("remove recovers a stale lock owned by a dead process", async () => {
  // Arrange
  const base = await mkdtemp(path.join(tmpdir(), "host-artifact-")); const root = path.join(base, "public");
  const lock = path.join(root, "v2", "workspaces", workspace, "artifacts", "report.lock");
  await mkdir(path.join(root, "v2", "workspaces", workspace, "artifacts", "report"), { recursive: true });
  await createCrashedShlock(lock);

  // Act & Assert
  await removeArtifact({ root, workspace, name: "report", lockAttempts: 50 });
  await assert.rejects(readdir(path.join(root, "v2", "workspaces", workspace, "artifacts", "report")));
});

test("publish never steals a lock owned by a live process", async () => {
  // Arrange
  const base = await mkdtemp(path.join(tmpdir(), "host-artifact-")); const root = path.join(base, "public"); const source = path.join(base, "report.html");
  const lock = path.join(root, "v2", "workspaces", workspace, "artifacts", "report.lock");
  await mkdir(path.dirname(lock), { recursive: true }); await writeFile(lock, `${process.pid}\n`); await writeFile(source, "content");

  // Act & Assert
  await assert.rejects(publishArtifact(source, { root, workspace, name: "report", lockAttempts: 1 }), /lock acquisition timed out/);
  assert.equal((await readFile(lock, "utf8")).trim(), String(process.pid));
});

test("concurrent stale lock recoverers never delete the newly acquired live lock", async () => {
  // Arrange: 二つの publisher が同じ stale lock を同時に観測する。
  const base = await mkdtemp(path.join(tmpdir(), "host-artifact-")); const root = path.join(base, "public");
  const first = path.join(base, "first.html"); const second = path.join(base, "second.html");
  const lock = path.join(root, "v2", "workspaces", workspace, "artifacts", "report.lock");
  await createCrashedShlock(lock);
  await writeFile(first, "first"); await writeFile(second, "second");

  // Act
  const results = await Promise.all([
    publishArtifact(first, { root, workspace, name: "report", revisionGenerator: () => `r-${"3".repeat(32)}` }),
    publishArtifact(second, { root, workspace, name: "report", revisionGenerator: () => `r-${"4".repeat(32)}` }),
  ]);

  // Assert: 両 writer が直列化され、後から取得した lock を stale cleanup が消していない。
  assert.deepEqual(new Set(results.map((item) => item.revision)), new Set([`r-${"3".repeat(32)}`, `r-${"4".repeat(32)}`]));
  const artifactRoot = path.join(root, "v2", "workspaces", workspace, "artifacts", "report");
  assert.equal((await readdir(path.join(artifactRoot, "revisions"))).length, 2);
});
