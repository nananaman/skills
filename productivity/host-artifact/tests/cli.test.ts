import assert from "node:assert/strict";
import test from "node:test";
import {
  buildArtifactUrl,
  ensureReady,
  getReadyTailscaleAddress,
  hasReadyTailscaleListener,
  isExpectedHealth,
  publishVerified,
  waitForArtifact,
} from "../src/cli-lib.js";

test("healthy service does not invoke the ensure wrapper", async () => {
  // Arrange
  let ensureCalls = 0;

  // Act
  await ensureReady({
    isHealthy: async () => true,
    ensureService: async () => { ensureCalls++; },
  });

  // Assert
  assert.equal(ensureCalls, 0);
});

test("unhealthy service invokes the fixed ensure wrapper and verifies recovery", async () => {
  // Arrange
  let healthCalls = 0;
  let ensureCalls = 0;

  // Act
  await ensureReady({
    isHealthy: async () => ++healthCalls > 1,
    ensureService: async () => { ensureCalls++; },
  });

  // Assert
  assert.equal(ensureCalls, 1);
  assert.equal(healthCalls, 2);
});

test("failed recovery is reported instead of publishing", async () => {
  // Arrange
  const dependencies = {
    isHealthy: async () => false,
    ensureService: async () => undefined,
  };

  // Act & Assert
  await assert.rejects(ensureReady(dependencies), /unavailable/i);
});

test("health validation rejects unrelated successful JSON responses", async () => {
  // Arrange & Act
  const valid = isExpectedHealth(200, { service: "host-artifact", version: 1, status: "ok" });
  const unrelated = isExpectedHealth(200, { status: "ok" });

  // Assert
  assert.equal(valid, true);
  assert.equal(unrelated, false);
});

test("Tailscale readiness requires the expected health identity and a bound listener", () => {
  // Arrange & Act
  const ready = hasReadyTailscaleListener(200, {
    service: "host-artifact",
    version: 1,
    status: "ok",
    tailscaleReady: true,
    tailscaleAddress: "100.64.0.9",
  });
  const unbound = hasReadyTailscaleListener(200, {
    service: "host-artifact",
    version: 1,
    status: "ok",
    tailscaleReady: false,
  });

  // Assert
  assert.equal(ready, true);
  assert.equal(unbound, false);
});

test("Tailscale address is returned only for a ready listener", () => {
  // Arrange & Act
  const ready = getReadyTailscaleAddress(200, {
    service: "host-artifact",
    version: 1,
    status: "ok",
    tailscaleReady: true,
    tailscaleAddress: "100.64.0.9",
  });
  const unready = getReadyTailscaleAddress(200, {
    service: "host-artifact",
    version: 1,
    status: "ok",
    tailscaleReady: false,
    tailscaleAddress: "100.64.0.9",
  });

  // Assert
  assert.equal(ready, "100.64.0.9");
  assert.equal(unready, undefined);
});

test("artifact URL encodes each path segment without changing separators", () => {
  // Arrange & Act
  const url = buildArtifactUrl("http://localhost:9417", "local-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "資料 #?%/a b.html");

  // Assert
  assert.equal(url, "http://localhost:9417/local-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/%E8%B3%87%E6%96%99%20%23%3F%25/a%20b.html");
});

test("artifact verification accepts a delayed successful exact route", async () => {
  // Arrange
  let calls = 0;

  // Act
  const result = await waitForArtifact("http://example/artifact", {
    fetchStatus: async () => ++calls === 2 ? 200 : 404,
    wait: async () => undefined,
    attempts: 3,
  });

  // Assert
  assert.equal(result, true);
  assert.equal(calls, 2);
});

test("artifact verification rejects a wrong-root route after bounded attempts", async () => {
  // Arrange & Act
  const result = await waitForArtifact("http://example/artifact", {
    fetchStatus: async () => 404,
    wait: async () => undefined,
    attempts: 2,
  });

  // Assert
  assert.equal(result, false);
});

test("failed post-copy verification removes only the newly hosted artifact", async () => {
  // Arrange
  const remaining = new Set(["local-existing", "local-new"]);

  // Act & Assert
  await assert.rejects(publishVerified({
    publish: async () => ({ id: "local-new", relativePath: "report.html" }),
    verify: async () => { throw new Error("localhost route verification failed"); },
    remove: async (id) => { remaining.delete(id); },
  }), /localhost route verification failed/);
  assert.deepEqual([...remaining], ["local-existing"]);
});

test("cleanup failure reports both errors while preserving the verification failure as cause", async () => {
  // Arrange
  const primary = new Error("localhost route verification failed");

  // Act
  const error = await publishVerified({
    publish: async () => ({ id: "local-new", relativePath: "report.html" }),
    verify: async () => { throw primary; },
    remove: async () => { throw new Error("permission denied"); },
  }).catch((caught: unknown) => caught);

  // Assert
  assert(error instanceof Error);
  assert.match(error.message, /localhost route verification failed.*permission denied/);
  assert.equal(error.cause, primary);
});
