import assert from "node:assert/strict";
import test from "node:test";
import { isExpectedHealth, parseWorkspaceResult, selectTransport, waitForRevision } from "../src/cli-lib.js";

test("readiness accepts protocol v2 and rejects the legacy daemon", () => {
  assert.equal(isExpectedHealth(200, { service: "host-artifact", version: 2, status: "ok" }), true);
  assert.equal(isExpectedHealth(200, { service: "host-artifact", version: 1, status: "ok" }), false);
});

test("workspace helper parser accepts only the schema contract", () => {
  // Arrange & Act
  const result = parseWorkspaceResult({ schemaVersion: 1, status: "ok", workspace: { segment: "owner-repo~0123456789ab", displayName: "owner/repo" } });
  // Assert
  assert.equal(result.segment, "owner-repo~0123456789ab");
  assert.throws(() => parseWorkspaceResult({ segment: "/secret/path" }), /malformed/i);
});

test("configured and verified Tailscale uses remote URL", () => {
  const result = selectTransport("http://127.0.0.1/a/owner-repo~0123456789ab/report/", { schemaVersion: 1, available: true, configured: true, origin: "https://machine.ts.net" }, { schemaVersion: 1, verified: true, url: "https://machine.ts.net/a/owner-repo~0123456789ab/report/" });
  assert.deepEqual(result, { transport: "tailscale-serve", url: "https://machine.ts.net/a/owner-repo~0123456789ab/report/" });
});

test("missing or failed Tailscale verification degrades to localhost", () => {
  const local = "http://127.0.0.1/a/x/y/";
  assert.equal(selectTransport(local, { schemaVersion: 1, available: false, configured: false }).transport, "localhost");
  assert.equal(selectTransport(local, { schemaVersion: 1, available: true, configured: true, origin: "https://machine.ts.net" }, { schemaVersion: 1, verified: false, reason: "offline" }).url, local);
});

test("verified Tailscale URL must match inspected HTTPS origin and exact artifact path", () => {
  // Arrange
  const local = "http://127.0.0.1:9417/a/owner-repo~0123456789ab/report/";
  const inspect = { schemaVersion: 1, available: true, configured: true, origin: "https://machine.tailnet.ts.net/" };
  const invalid = [
    "http://machine.tailnet.ts.net/a/owner-repo~0123456789ab/report/",
    "https://other.tailnet.ts.net/a/owner-repo~0123456789ab/report/",
    "https://machine.tailnet.ts.net/a/owner-repo~0123456789ab/other/",
    "https://machine.tailnet.ts.net/a/owner-repo~0123456789ab/report/?token=x",
    "https://machine.tailnet.ts.net/a/owner-repo~0123456789ab/report/#fragment",
  ];

  // Act & Assert
  for (const url of invalid) assert.equal(selectTransport(local, inspect, { schemaVersion: 1, verified: true, url }).transport, "localhost");
});

test("local verification requires the expected revision header", async () => {
  const response = new Response("ok", { headers: { "X-Host-Artifact-Revision": `r-${"a".repeat(32)}` } });
  assert.equal(await waitForRevision("http://localhost/a/x/y/", `r-${"a".repeat(32)}`, async () => response), true);
});
