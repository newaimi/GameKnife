import assert from "node:assert/strict";
import test from "node:test";
import { communityFeatureEntries } from "@gameknife/feature-registry";
import { readToolLinkProps } from "../dist/components/toolLinkProps.js";

test("tool links only open a new tab when the registry requests it", () => {
  const manualEditTool = communityFeatureEntries.find((tool) => tool.id === "manual-edit");

  assert.equal(manualEditTool?.openInNewTab, true);
  assert.deepEqual(readToolLinkProps(), {});
  assert.deepEqual(readToolLinkProps(false), {});
  assert.deepEqual(readToolLinkProps(manualEditTool.openInNewTab), {
    target: "_blank",
    rel: "noopener noreferrer",
  });
});
