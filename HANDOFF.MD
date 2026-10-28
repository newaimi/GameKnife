# Maintenance handoff

## 2026-10-28: Sequence playback and independent saves

- This change fixes existing shared SequenceEditor behavior that is also consumed by Commercial. It does not add a new public workflow or alter Community's no-login boundary.
- Decode frame images before switching the visible frame. Keep the previous frame visible while the requested image is loading. Share Blob requests within the editor and release Object URLs on unmount; a rejected entry must be removed so retry can succeed.
- Playback must respect enabled frames, per-frame durations and the loop flag. Start the first frame's clock after it is decoded, and cancel a pending advance when playback stops.
- Keep settings and frame edits independent. Saving frame offsets must preserve unsaved FPS and cleaning parameters; saving settings must preserve unsaved frame edits. A complete server response or reference-frame change must not silently reset another draft.
- Saving FPS rescales positive frame durations in the SQLite transaction. A zero duration continues to mean that playback uses FPS. Use the same positive rounding rule as the browser, and retain workspace isolation and rollback behavior.
- Component tests exercise the actual SequenceWorkspace parent callbacks and refetches. A static SequenceEditor mock cannot detect a parent response resetting another draft.
- SequenceEditor has a fixed-size preview canvas. Use WorkbenchPreview's existing intrinsic content mode so its initial centering and fit control measure that canvas. The default fill mode measures the entire viewport and leaves the frame under the tool panel.
- Real browser acceptance used a separate temporary SQLite database and storage directory with generated images. Local model inference and optional model services were not required for this editor check.
