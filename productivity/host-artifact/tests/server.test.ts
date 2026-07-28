import assert from "node:assert/strict";
import { mkdtemp, mkdir, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { createArtifactApp } from "../src/app.js";
import { buildArtifactUrl } from "../src/cli-lib.js";

test("capability route serves static content with safe headers", async () => {
  // Arrange
  const root = await mkdtemp(path.join(tmpdir(), "host-artifact-"));
  const id = `local-${"c".repeat(32)}`;
  await mkdir(path.join(root, id));
  await writeFile(path.join(root, id, "report.html"), "<h1>ok</h1>");
  const app = createArtifactApp({ root });

  // Act
  const response = await app.request(`http://localhost/${id}/report.html`);

  // Assert
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /text\/html/);
  assert.equal(response.headers.get("cache-control"), "no-store");
  assert.equal(response.headers.get("x-content-type-options"), "nosniff");
  assert.equal(await response.text(), "<h1>ok</h1>");
});

test("root and unknown capability do not disclose an artifact listing", async () => {
  // Arrange
  const root = await mkdtemp(path.join(tmpdir(), "host-artifact-"));
  const app = createArtifactApp({ root });

  // Act
  const rootResponse = await app.request("http://localhost/");
  const unknownResponse = await app.request(`http://localhost/local-${"d".repeat(32)}/index.html`);

  // Assert
  assert.equal(rootResponse.status, 404);
  assert.equal(unknownResponse.status, 404);
});

test("health endpoint reports readiness without listing artifacts", async () => {
  // Arrange
  const root = await mkdtemp(path.join(tmpdir(), "host-artifact-"));
  const app = createArtifactApp({ root });

  // Act
  const response = await app.request("http://localhost/.well-known/host-artifact/health");

  // Assert
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), { service: "host-artifact", version: 1, status: "ok" });
});

test("health endpoint reports whether the Tailscale listener is bound", async () => {
  // Arrange
  const root = await mkdtemp(path.join(tmpdir(), "host-artifact-"));
  const app = createArtifactApp({
    root,
    tailscaleState: () => ({ ready: true, address: "100.64.0.9" }),
  });

  // Act
  const response = await app.request("http://localhost/.well-known/host-artifact/health");

  // Assert
  assert.deepEqual(await response.json(), {
    service: "host-artifact",
    version: 1,
    status: "ok",
    tailscaleReady: true,
    tailscaleAddress: "100.64.0.9",
  });
});

test("encoded traversal and dotfile paths are not served", async () => {
  // Arrange
  const root = await mkdtemp(path.join(tmpdir(), "host-artifact-"));
  const id = `local-${"f".repeat(32)}`;
  await mkdir(path.join(root, id));
  await writeFile(path.join(root, id, ".secret"), "secret");
  const app = createArtifactApp({ root });

  // Act
  const traversal = await app.request(`http://localhost/${id}/%2e%2e/secret`);
  const dotfile = await app.request(`http://localhost/${id}/.secret`);

  // Assert
  assert.equal(traversal.status, 404);
  assert.equal(dotfile.status, 404);
});

test("a symlink added to the publish tree is not served", async () => {
  // Arrange
  const root = await mkdtemp(path.join(tmpdir(), "host-artifact-"));
  const id = `local-${"9".repeat(32)}`;
  await mkdir(path.join(root, id));
  await writeFile(path.join(root, id, "content.html"), "content");
  await symlink("content.html", path.join(root, id, "alias.html"));
  const app = createArtifactApp({ root });

  // Act
  const response = await app.request(`http://localhost/${id}/alias.html`);

  // Assert
  assert.equal(response.status, 404);
});

test("Tailscale app rejects local artifacts and serves tailscale artifacts", async () => {
  // Arrange
  const root = await mkdtemp(path.join(tmpdir(), "host-artifact-"));
  const localId = `local-${"7".repeat(32)}`;
  const remoteId = `tailscale-${"8".repeat(32)}`;
  for (const id of [localId, remoteId]) {
    await mkdir(path.join(root, id));
    await writeFile(path.join(root, id, "index.html"), id);
  }
  const app = createArtifactApp({ root, exposure: "tailscale" });

  // Act
  const local = await app.request(`http://localhost/${localId}/index.html`);
  const remote = await app.request(`http://localhost/${remoteId}/index.html`);

  // Assert
  assert.equal(local.status, 404);
  assert.equal(remote.status, 200);
});

test("encoded spaces delimiters percent and non-ASCII roundtrip to the same file", async () => {
  // Arrange
  const root = await mkdtemp(path.join(tmpdir(), "host-artifact-"));
  const id = `local-${"6".repeat(32)}`;
  const relativePath = "資料 #?%/a b.html";
  await mkdir(path.join(root, id, "資料 #?%"), { recursive: true });
  await writeFile(path.join(root, id, relativePath), "encoded");
  const app = createArtifactApp({ root });
  const url = buildArtifactUrl("http://localhost", id, relativePath);

  // Act
  const response = await app.request(url);

  // Assert
  assert.equal(response.status, 200);
  assert.equal(await response.text(), "encoded");
});
