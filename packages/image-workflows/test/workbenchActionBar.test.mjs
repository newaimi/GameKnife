import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { I18nextProvider } from "react-i18next";
import { createGameKnifeI18n } from "@gameknife/i18n";
import {
  ImageSequenceUploadAction,
  ImageUploadAction,
  VideoUploadAction,
  WorkbenchActionBar,
} from "../dist/components/WorkbenchActionBar.js";
import { readManualEditorActionState } from "../dist/workspaces/manual-edit/manualEditorActionState.js";

test("WorkbenchActionBar exposes one translated toolbar for primary workflow actions", async () => {
  const i18n = await createGameKnifeI18n({ initialLanguage: "en", detectLanguage: false });
  const markup = renderToStaticMarkup(
    createElement(
      I18nextProvider,
      { i18n },
      createElement(WorkbenchActionBar, null, createElement("button", { type: "button" }, "Process")),
    ),
  );

  assert.match(markup, /class="workbench-action-bar no-pan"/);
  assert.match(markup, /role="toolbar"/);
  assert.match(markup, /aria-label="Workbench actions"/);
  assert.match(markup, />Process</);
});

test("upload actions keep file scopes and disabled state explicit", () => {
  const imageMarkup = renderToStaticMarkup(createElement(ImageUploadAction, { label: "Upload image", disabled: true, onFile() {} }));
  const sequenceMarkup = renderToStaticMarkup(createElement(ImageSequenceUploadAction, { label: "Upload sequence", onFiles() {} }));
  const videoMarkup = renderToStaticMarkup(createElement(VideoUploadAction, { label: "Upload video", onFile() {} }));

  assert.match(imageMarkup, /accept="image\/jpeg,image\/png,image\/webp"/);
  assert.match(imageMarkup, /aria-disabled="true"/);
  assert.match(imageMarkup, /disabled=""/);
  assert.match(sequenceMarkup, /multiple=""/);
  assert.match(videoMarkup, /accept="video\/mp4,video\/webm,video\/quicktime,.mp4,.webm,.mov"/);
});

test("manual editor action states keep each command dependency explicit", () => {
  assert.deepEqual(
    readManualEditorActionState({ hasSource: false, canWrite: true, saving: false, canUndo: false, canRedo: false }),
    {
      uploadDisabled: false,
      undoDisabled: true,
      redoDisabled: true,
      saveDisabled: true,
      exportDisabled: true,
    },
  );

  assert.deepEqual(
    readManualEditorActionState({ hasSource: true, canWrite: false, saving: true, canUndo: true, canRedo: false }),
    {
      uploadDisabled: true,
      undoDisabled: false,
      redoDisabled: true,
      saveDisabled: true,
      exportDisabled: false,
    },
  );
});
