White backgrounds and one continuation action

White-background edits previously preserved invented scenery, and result cards repeated their prompt through generated titles and extra actions. Whole-image generation and editing now append the requested pure-white instruction, masked edits omit it, and Continue editing inherits its input node's White bg setting. Cards, preview surfaces, and prompt boxes are white in every state.

Result cards have one forward action: Continue editing. Reroll/revision buttons and the result reroll shortcut are removed. New, continued, and duplicated nodes start unnamed; people can name them or clear their names. Untitled references consistently use the first five prompt words, falling back to “Image” only when no words exist. The header's naming placeholder appears only on hover or focus.

White bg appears on every node. Running nodes and results display it disabled to respect the existing frozen-settings rule; the inherited setting is editable on the continued draft. Generation uses “Place the object on a plain pure white background.” Whole-image edits append “The background must be plain pure white.” The preservation preamble mentions background only when White bg is off.

UI audit (amendment §5)

The original consolidated brief and its seven confirmation cases were not present in the supplied context or repository. This audit uses the amendment and existing lifecycle/workflow documentation; uncertain retained features are explicitly flagged below rather than represented as confirmed brief requirements. Reviewed all graph components, project components, app pages, graph state/actions, keyboard shortcuts, and confirmation call sites.

| UI found | Decision and reason |
| --- | --- |
| Result / Draft / Running / Failed captions below headers | Deleted; status is already conveyed by the card, progress, errors, or frozen image. |
| Try another / Revise prompt, including result Cmd/Ctrl+D | Deleted; Continue editing is the sole forward action. |
| Generated node titles and duplicate “· copy” names | Deleted production generation code and auto-title tests; defaults are empty, and empty title edits persist. |
| Untitled header placeholder | Hidden at rest; “Name this node” appears only on header hover/focus. |
| Inspect icon plus clickable image | Deleted icon; image click is the inspection entry point, including when showing a mesh preview. |
| Deleted-input disconnect in both menu and warning | Deleted menu duplicate; retained-input recovery uses the warning action because its source wire is gone. |
| Input/chip/wire numbers for one input | Hidden; numbering remains for two or more incoming images. The wire removal target remains available on hover/focus. |
| 2D / 3D preview pair | Retained only when the active image has a loaded matching mesh preview. |
| Long 3D title and back-to-canvas caption | Replaced with “3D view” and “Close”. Other image/collapse close captions also use “Close”. |
| 3D caveat paragraph | Shortened to “Hidden sides are inferred and may vary.” Full text is in an expandable, keyboard-accessible info control. |
| 3D generation explanation, “Colors and print included”, saved/completion timing, interaction tips | Deleted redundant copy; progress uses Queued / Generating / Saving and elapsed seconds, plus “Safe to close — this keeps running.” |
| Legacy image-strip explanation | Deleted; thumbnails identify the selectable images. |
| Image-inspection heading/tips and timestamp captions | Removed single-image heading, tips, and timestamps; retained captions identify sources and the comparison heading identifies the two-pane view. |
| Empty-project second New Project button and prose | Deleted; the header owns New Project. |
| Mask editor's “3px blended seam” explanation | Removed implementation detail; retained “Orange areas change” to explain the selection overlay. |
| Gray preview, subject-chip, reference-chip, running-prompt surfaces and resting card shadow | Removed; surfaces are white, with hover/selection feedback. Image inspection and 3D dialog surfaces are also white. |
| Save dots at card and workspace level | Flagged/retained: icon-only feedback distinguishes a failed individual save from workspace persistence; no resting “Saved” text is rendered. Accessible status names remain. |
| Duplicate draft and its keyboard shortcut | Flagged/retained: applies only to unfinished drafts under the existing lifecycle; cannot reroll a result. |
| Collapse-chain edit count/action | Flagged/retained: documented chain-compaction workflow, shown only after at least two edits; it has one visible entry point. |
| Legacy multi-image strip | Flagged/retained: needed to access existing stored images; absent for single-image nodes. |
| Six-rule help panel, shortcut table, empty-canvas three-step introduction | Flagged/retained: existing lifecycle documentation identifies these as requested; help is opt-in, and the introduction appears only before the first node. |
| Project timestamps, Rename/Delete, canvas zoom/fit, image zoom/fit/download, Compare | Flagged/retained: existing navigation, project management, inspection, and export functions; Compare requires exactly two image nodes. Keyboard/gesture access remains alongside the single visible control. |
| Mask tools, selection counts, empty/full/stale-selection messages and outside-selection metric | Flagged/retained: communicate the selected area and preservation result, including cases where the mask cannot safely run. |
| Reference limits, 7,500+ character counter, broken-source and conflict recovery copy | Flagged/retained: shown only at the relevant limit/error; explains why editing or Run is blocked and how to recover. |
| Error-recovery actions resembling chip/wire actions | Flagged/retained: contextual recovery for missing/deleted sources, invalid masks, or unsaved conflicts; needed when normal source controls are unavailable. |
| Textureless legacy mesh upgrade | Flagged/retained: offered only for an existing shape-only model; explains why another generation would add missing color. |
| React Flow attribution | Flagged/retained: library attribution, not a product workflow. |

Confirmation inventory (no new confirmations introduced)

| Existing case | Decision / justification |
| --- | --- |
| Delete project | Flagged/retained: removes access to the project from the project list. |
| Delete node with an image or dependents | Flagged/retained: explains image removal/retention and effects on connected nodes. |
| Delete node with unsaved changes | Flagged/retained: prevents accidental loss of local work. |
| Delete multiple nodes/wires | Flagged/retained: one combined confirmation covers the selected items. |
| Disconnect an input with a saved selection | Flagged/retained: the selection must be cleared with its input. |
| Use saved draft after a conflict | Flagged/retained: discards the locally edited draft. |
| Leave with unsaved work (Projects navigation or browser unload) | Flagged/retained: protects pending local edits; these are two navigation mechanisms for the same condition. |

Unmasked disconnection, single reference removal, and deletion of an unused empty node do not confirm. Paid image and mesh generation use their explicit Run/Generate buttons, with no added confirmation step.

Validation and limits

- Backend suite: 100 passed; seven PostgreSQL-only checks skipped without TEST_DATABASE_URL. Tests exercise real API/freezing/worker paths with a fake provider, including three-edit inheritance with White bg both on and off, blank titles across runs, and masked prompt exclusion.
- Browser checks cover computed #FFFFFF surfaces, blank-name persistence, continuation settings, frozen/running toggle visibility, one forward action, conditional numbering, references, masking, 3D cache/preview conditions, and legacy images. 34 distinct browser tests passed across the targeted runs (nine canvas, ten cleanup, five lifecycle, four masking, two mesh, two legacy/result, two amendment).
- Production build, TypeScript, ESLint, Ruff and the two frontend unit tests pass.
- No live paid provider generation was run. Prompt propagation is verified; pure-white output pixels after a real three-edit chain still need visual acceptance against the provider.
- Existing stored title strings have no human/automatic provenance. This change stops all future automatic naming but does not erase existing titles, which could destroy names people entered. Old titles can be cleared using the now-persistent empty title field; identifying historical automatic titles needs provenance or a user-selected cleanup list.
- This is a prepared PR description in the working tree; no remote PR has been opened or existing unrelated work committed.
