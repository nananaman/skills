import assert from "node:assert/strict";
import test from "node:test";
import { withLiveReload } from "../src/live-reload.js";

test("live reload embeds the displayed source version for the first poll", () => {
  // Arrange
  const source = "<h1>progress</h1>";

  // Act
  const transformed = withLiveReload(source);

  // Assert
  assert.match(transformed, /data-host-artifact-version="[a-f0-9]{64}"/);
  assert.match(transformed, /const currentVersion = "[a-f0-9]{64}"/);
});

test("live reload does not mistake source marker text or body-like script text for generated markup", () => {
  // Arrange
  const source = `<script>const example = "</body> data-host-artifact-live-reload";</script>`;

  // Act
  const transformed = withLiveReload(source);

  // Assert
  assert.equal(transformed.startsWith(source), true);
  assert.equal(transformed.match(/<script data-host-artifact-live-reload/g)?.length, 1);
});

test("live reload preserves non-UTF-8 source bytes", () => {
  // Arrange
  const source = Buffer.from([0x3c, 0x68, 0x31, 0x3e, 0x82, 0xa0, 0x3c, 0x2f, 0x68, 0x31, 0x3e]);

  // Act
  const transformed = withLiveReload(source);

  // Assert
  assert.deepEqual(transformed.subarray(0, source.length), source);
});

test("live reload replaces a previously generated script instead of appending another", () => {
  // Arrange
  const source = "<h1>progress</h1>";
  const previouslyHosted = withLiveReload(source);

  // Act
  const transformed = withLiveReload(previouslyHosted);

  // Assert
  assert.equal(transformed.match(/<script data-host-artifact-live-reload/g)?.length, 1);
});

test("live reload preserves user content that contains the reserved script prefix", () => {
  // Arrange
  const source = `<script>const example = '<script data-host-artifact-live-reload data-host-artifact-version="${"a".repeat(64)}">';</script>`;

  // Act
  const transformed = withLiveReload(source);

  // Assert
  assert.equal(transformed.startsWith(source), true);
  assert.equal(transformed.match(/<script data-host-artifact-live-reload/g)?.length, 2);
});
