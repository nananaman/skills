import assert from "node:assert/strict";
import test from "node:test";
import { detectTailscaleIPv4 } from "../src/tailscale.js";

test("network detection accepts only the authoritative Tailscale address present on an interface", () => {
  // Arrange
  const interfaces = {
    en0: [{ address: "100.64.0.2", family: "IPv4", internal: false }],
    utun4: [{ address: "100.64.0.3", family: "IPv4", internal: false }],
  };

  // Act
  const address = detectTailscaleIPv4("100.64.0.3", () => interfaces);

  // Assert
  assert.equal(address, "100.64.0.3");
});

test("network detection rejects a CGNAT VPN address that differs from Tailscale", () => {
  // Arrange
  const interfaces = {
    utun4: [{ address: "100.64.0.3", family: "IPv4", internal: false }],
  };

  // Act
  const address = detectTailscaleIPv4("100.65.0.4", () => interfaces);

  // Assert
  assert.equal(address, undefined);
});
