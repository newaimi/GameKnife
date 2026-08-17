import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import {
  ImageSequenceUploadAction,
  ImageUploadAction,
  VideoUploadAction,
  WorkbenchActionBar,
} from "../dist/components/WorkbenchActionBar.js";

test("WorkbenchActionBar exposes one toolbar for primary workflow actions", () => {
  const markup = renderToStaticMarkup(
    createElement(WorkbenchActionBar, null, createElement("button", { type: "button" }, "开始处理")),
  );

  assert.match(markup, /class="workbench-action-bar no-pan"/);
  assert.match(markup, /role="toolbar"/);
  assert.match(markup, /aria-label="工作台操作"/);
  assert.match(markup, />开始处理</);
});

test("upload actions keep file scopes and disabled state explicit", () => {
  const imageMarkup = renderToStaticMarkup(createElement(ImageUploadAction, { label: "上传图片", disabled: true, onFile() {} }));
  const sequenceMarkup = renderToStaticMarkup(createElement(ImageSequenceUploadAction, { label: "上传序列", onFiles() {} }));
  const videoMarkup = renderToStaticMarkup(createElement(VideoUploadAction, { label: "上传视频", onFile() {} }));

  assert.match(imageMarkup, /accept="image\/jpeg,image\/png,image\/webp"/);
  assert.match(imageMarkup, /aria-disabled="true"/);
  assert.match(imageMarkup, /disabled=""/);
  assert.match(sequenceMarkup, /multiple=""/);
  assert.match(videoMarkup, /accept="video\/mp4,video\/webm,video\/quicktime,.mp4,.webm,.mov"/);
});
