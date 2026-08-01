import assert from "node:assert/strict";
import { mkdtemp, mkdir, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { createArtifactApp } from "../src/app.js";
import { publishArtifact } from "../src/publisher.js";

const workspace = "nananaman-skills~0123456789ab";

test("named route serves only current revision with revision and safe cache headers", async () => {
  // Arrange
  const base = await mkdtemp(path.join(tmpdir(), "host-artifact-"));
  const root = path.join(base, "public");
  const source = path.join(base, "report.html");
  await mkdir(root);
  await writeFile(source, "report");
  const published = await publishArtifact(source, { root, workspace, name: "report", revisionGenerator: () => "r-" + "4".repeat(32) });
  const app = createArtifactApp({ root });

  // Act
  const response = await app.request(`http://localhost${published.route}`);
  const head = await app.request(`http://localhost${published.route}`, { method: "HEAD" });

  // Assert
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("x-host-artifact-revision"), published.revision);
  assert.equal(response.headers.get("cache-control"), "no-store");
  assert.match(response.headers.get("etag") ?? "", /^"[a-f0-9]{64}"$/);
  assert.equal(head.headers.get("etag"), response.headers.get("etag"));
  assert.equal(await head.text(), "");
});

test("shelf lists valid current artifacts and ignores legacy and corrupt entries", async () => {
  // Arrange
  const base = await mkdtemp(path.join(tmpdir(), "host-artifact-"));
  const root = path.join(base, "public");
  const source = path.join(base, "diagram.svg");
  await mkdir(path.join(root, "local-" + "f".repeat(32)), { recursive: true });
  await writeFile(path.join(root, "local-" + "f".repeat(32), "old.html"), "legacy");
  await writeFile(source, "<svg></svg>");
  await publishArtifact(source, { root, workspace, name: "diagram", revisionGenerator: () => "r-" + "5".repeat(32) });
  await mkdir(path.join(root, "v2", "workspaces", workspace, "artifacts", "broken"), { recursive: true });
  await writeFile(path.join(root, "v2", "workspaces", workspace, "artifacts", "broken", "current.json"), "{");
  const app = createArtifactApp({ root });

  // Act
  const response = await app.request("http://localhost/");
  const body = await response.text();

  // Assert
  assert.equal(response.status, 200);
  assert.match(body, new RegExp(`/a/${workspace}/diagram/`));
  assert.doesNotMatch(body, /legacy|broken/);
});

test("legacy capability route and traversal are unavailable", async () => {
  // Arrange
  const root = await mkdtemp(path.join(tmpdir(), "host-artifact-"));
  const app = createArtifactApp({ root });

  // Act & Assert
  assert.equal((await app.request(`http://localhost/local-${"a".repeat(32)}/index.html`)).status, 404);
  assert.equal((await app.request(`http://localhost/a/${workspace}/report/%252e%252e/current.json`)).status, 404);
});

test("health endpoint exposes protocol version 2", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "host-artifact-"));
  const response = await createArtifactApp({ root }).request("http://localhost/.well-known/host-artifact/health");
  assert.deepEqual(await response.json(), { service: "host-artifact", version: 2, status: "ok" });
});

test("symlinked revision root never serves content outside the publish root", async () => {
  // Arrange: valid-looking current metadata points at a revision symlink.
  const base = await mkdtemp(path.join(tmpdir(), "host-artifact-")); const root = path.join(base, "public"); const outside = path.join(base, "outside");
  const artifactRoot = path.join(root, "v2", "workspaces", workspace, "artifacts", "report"); const revision = `r-${"9".repeat(32)}`;
  await mkdir(path.join(artifactRoot, "revisions"), { recursive: true }); await mkdir(outside); await writeFile(path.join(outside, "report.html"), "secret outside");
  await symlink(outside, path.join(artifactRoot, "revisions", revision));
  await writeFile(path.join(artifactRoot, "current.json"), JSON.stringify({ schemaVersion: 1, workspace, name: "report", revision, kind: "html", entry: "report.html", updatedAt: new Date().toISOString() }));

  // Act
  const response = await createArtifactApp({ root }).request(`http://localhost/a/${workspace}/report/`);

  // Assert
  assert.equal(response.status, 404);
});

test("directory artifact serves nested wildcard asset bytes with its own MIME type", async () => {
  // Arrange: entry HTML と異なる nested asset を持つ directory artifact。
  const base = await mkdtemp(path.join(tmpdir(), "host-artifact-")); const root = path.join(base, "public"); const source = path.join(base, "site");
  await mkdir(root); await mkdir(path.join(source, "assets"), { recursive: true });
  await writeFile(path.join(source, "index.html"), "<h1>entry</h1>"); await writeFile(path.join(source, "assets", "app.css"), "body{color:red}");
  await publishArtifact(source, { root, workspace, name: "site", revisionGenerator: () => `r-${"8".repeat(32)}` });

  // Act
  const response = await createArtifactApp({ root }).request(`http://localhost/a/${workspace}/site/assets/app.css`);

  // Assert
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /text\/css/);
  assert.equal(await response.text(), "body{color:red}");
});

test("directory artifact preserves literal percent and percent-like filenames", async () => {
  // Arrange
  const base = await mkdtemp(path.join(tmpdir(), "host-artifact-")); const root = path.join(base, "public"); const source = path.join(base, "site");
  await mkdir(root); await mkdir(source); await writeFile(path.join(source, "index.html"), "entry");
  await writeFile(path.join(source, "logo%.svg"), "literal-percent"); await writeFile(path.join(source, "logo%20final.svg"), "literal-percent-20");
  await publishArtifact(source, { root, workspace, name: "percent-site", revisionGenerator: () => `r-${"7".repeat(32)}` });
  const app = createArtifactApp({ root });

  // Act
  const percent = await app.request(`http://localhost/a/${workspace}/percent-site/logo%25.svg`);
  const percentLike = await app.request(`http://localhost/a/${workspace}/percent-site/logo%2520final.svg`);

  // Assert
  assert.equal(await percent.text(), "literal-percent");
  assert.equal(await percentLike.text(), "literal-percent-20");
  assert.match(percentLike.headers.get("content-type") ?? "", /image\/svg\+xml/);
});

test("directory artifact rejects encoded traversal instead of decoding it twice", async () => {
  // Arrange
  const base = await mkdtemp(path.join(tmpdir(), "host-artifact-")); const root = path.join(base, "public"); const source = path.join(base, "site");
  await mkdir(root); await mkdir(source); await writeFile(path.join(source, "index.html"), "entry");
  await publishArtifact(source, { root, workspace, name: "safe-site", revisionGenerator: () => `r-${"6".repeat(32)}` });

  // Act
  const response = await createArtifactApp({ root }).request(`http://localhost/a/${workspace}/safe-site/%252e%252e/current.json`);

  // Assert
  assert.equal(response.status, 404);
});
