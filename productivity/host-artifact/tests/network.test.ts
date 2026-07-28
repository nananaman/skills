import assert from "node:assert/strict";
import test from "node:test";
import { detectTailscaleIPv4 } from "../src/tailscale.js";

test("network detection accepts CGNAT IPv4 only on Tailscale-like interfaces", () => {
  // Arrange
  const interfaces = {
    en0: [{ address: "100.64.0.2", family: "IPv4", internal: false }],
    utun4: [{ address: "100.64.0.3", family: "IPv4", internal: false }],
  };

  // Act
  const address = detectTailscaleIPv4(() => interfaces);

  // Assert
  assert.equal(address, "100.64.0.3");
});
