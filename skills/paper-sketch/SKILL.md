---
name: paper-sketch
description: Generate scientific diagrams with imagegen and statistical plots with Python/Matplotlib using preserved PaperBanana agents, real reference examples, and Codex reasoning. Refine saved diagrams from user feedback; inspect and select saved diagram or plot versions.
---

# PaperSketch

The default CLI uses the synchronous execution copy in `assets/sync/`. Its Diagram implementation is converted from the preserved Python sources in `assets/interact/`. Keep its style guide, processor loops, state fields and non-retrieval prompts intact. Auto retrieval intentionally uses the approved four-group selection adapter described below. The pinned Interact commit and hashes of the 28 preserved files are in `assets/interact/SOURCE_MANIFEST.json`; `omitted_files` records the two removed provider files, their original hashes and removal reasons. Its Apache-2.0 license is in `assets/interact/LICENSE`. The base PaperBanana skill informed the setup/usage/output structure; its API-key runner is not this backend.

For statistical plots from numerical data, read [references/plot.md](references/plot.md) and use `--task plot`. That mode uses the synchronous copy derived from `assets/paperbanana_plot/`, Codex text/code calls, and local Matplotlib instead of imagegen. Its source commit, exact copy hashes and explicit path/import/execution-hook changes are in its `SOURCE_MANIFEST.json`. Do not run the diagram feedback procedure on plots.

## Environment and host contract

`<skill>` below is this skill's absolute folder. If it contains `installation.json`, `<runtime>` is `<skill>` itself: the installer includes data, pyproject.toml, uv.lock and a dedicated `.venv` there. Otherwise, for a development checkout, `<runtime>` is the repository root containing `skills/paper-sketch`, `data`, pyproject.toml and uv.lock. Never require the original development path or use paths recorded as historical provenance in manifests.

Run every `python` command below with `<runtime>/.venv/Scripts/python.exe` on Windows or `<runtime>/.venv/bin/python` on macOS/Linux; activation is unnecessary. For environment setup/repair use `uv sync --locked --no-dev --python 3.11 --project "<runtime>"`. Do not move an existing `.venv`; rebuild it at the destination. Python 3.11 is tested; upstream recommends 3.12. requirements.txt remains the runtime dependency list, while the installed environment uses uv.lock. To recheck an installed copy, use its Python to run `<skill>/scripts/verify_install.py`; this verifies local files, data and imports without invoking a model. It does not verify Codex login or imagegen availability.

The Google SDK provides original message/config types. The runner substitutes the generation module before importing agents, without initializing providers or looking up API keys. Python writes requests and waits; **the active Codex chat must service them**. Running the command alone does not invoke host tools and will eventually time out. Grouped retrieval and PBInteract text requests use independent Codex executions below. Original sampling, size tiers, and text-provider retries are not reproduced. Image retries follow the classified host policy below rather than the provider's exception/backoff logic. Do not fall back to a paid API or install this skill globally as part of a figure request.

Supported scope: diagram, one candidate, full initial generation, PBInteract feedback, completed-turn continuation and version selection; plots support initial full generation, inspect and version selection. Plot PBInteract feedback, simultaneous candidates, manual-reference mode, other refiners, external evaluation/simulation, arbitrary upstream UI/batch-session import, and interrupted-run recovery are not connected. The remaining generation and feedback sections describe diagrams; plot-specific execution is in references/plot.md.

The unused `configs/model_config.template.yaml` and original `utils/generation_utils.py` are not shipped. Do not create a provider API-key configuration for this runner. `scripts/bridge.py` must register the compatible generation module before importing agents; the original function names still resolve to the host bridge. Keep the Google SDK dependency for message/config types.

## Normal execution and permission boundaries

Before the first model-assisted figure task, establish the processing scope once. First check the current conversation and applicable user-approved project instructions for an explicit existing approval covering the same data and destinations. Reuse that approval rather than asking again. A request to install the skill, a saved result, an assistant-written acknowledgement, or this skill's instructions alone is not approval.

If no matching approval exists, ask one concise question before inference: "May PaperSketch process the research input and figures you explicitly provide for generation/refinement, including unpublished material, together with necessary public references and relevant saved history, using your ChatGPT-authenticated Codex service and built-in imagegen? Plot code will run locally. This scope will apply to later tasks in this conversation unless you change or revoke it." Use the host's user-input tool when available. Wait for the user's answer; do not send model requests on silence or refusal. Offline setup, inspection and data checks do not require this inference confirmation.

After approval, briefly acknowledge the agreed data, services and conversation/project scope in the chat, then proceed. For later figures, retries, Critic rounds, continuation and feedback inside that same scope, do not ask again. A new figure or new user-supplied methodology is not itself a scope expansion. Ask only about a concrete expansion, such as another service/account, unrelated local files or a new purpose. Respect a refusal, narrower approval or revocation immediately.

Approval is scoped, not a global installation preference. In a new chat, reuse it only if an applicable explicit user-approved project instruction or accessible user approval establishes that scope there; otherwise confirm once in the new chat. Do not create a global consent flag or treat a copied run/installation receipt as authorization. Do not edit project/global instructions to manufacture approval. Use only the supplied task input, necessary public references and relevant saved figure/history within the agreed scope.

Keep the actual execution boundaries clear:

- `run.py generate/refine` for diagrams starts a local coordinator: it reads local data, writes request/checkpoint files in the chosen output folder, and waits for responses. It does not itself start Codex CLI or call a provider API. Start it with ordinary workspace permissions where available; do not preemptively request elevated execution. If a sandbox error requires approval, describe the exact local filesystem operation and the later, separate inference steps accurately.
- `respond_retrieval.py` and `respond_text.py` invoke the existing ChatGPT-authenticated Codex CLI for text inference. They send that request's explicit text and any attached images to the configured Codex service. Diagram image requests are handled separately by the host's built-in imagegen tool with the prepared rendering prompt. The routing labels in the original record are not provider destinations; no Google API key is used.
- Plot code executes locally through Matplotlib; its text/code inference uses the same Codex host. A local coordinator waiting for a response is not evidence that a model call has already occurred.

For an actual automatic-review denial, retain the denied command and stated reason and respect the decision. Do not retry the same denied action with changed wording, split it to evade review, disable approval controls, or claim that these instructions authorize a transmission. Explain the specific blocker only when it actually occurs; do not turn it into a consent gate for every figure request.

## Synchronous execution

The run.py, probe.py and reference_probe.py CLI entry points dispatch to `assets/sync/scripts/`. Those functions are ordinary synchronous functions: model-response polling uses `time.monotonic` and `time.sleep`, blob I/O uses standard file operations, image conversion runs directly, and Plot rendering still uses the existing subprocess timeout. No asyncio event loop, local socketpair, or async startup probe is required. Model/host permissions remain a separate boundary.

The outer scripts and original vendor snapshots remain available for provenance and legacy regression comparisons; their async Python functions are not the production CLI. Do not call their async API directly or add an asyncio.run wrapper to execute the CLI. Keep using the documented commands. The prepared reference data stays at `<runtime>/data`, independently of the generated execution directory.

`assets/sync/SYNC_MANIFEST.json` records every original source hash and execution-copy hash. Original source/adapter changes require the developer command `python scripts/build_sync_runtime.py` from a checkout, followed by verification; the installer ships the built copy and checks both source and generated hashes. Generation is static, not an event-loop shim. Agent prompts, stage order, retry/timeout rules, review validation and immutable results remain the same for the supported single-candidate workflow. Parallel batches and other upstream UI/evaluation paths are still unsupported; do not infer support from converted unused functions. The offline style-guide generation source is preserved for provenance and is not a supported runtime command.

## Reference data

Use `<runtime>/data/diagram/` for the retained 298 diagram references. Duplicate downloads and evaluation splits were removed from this project's local data tree; original reference JSON, dataset documentation/license, and the download manifest remain as provenance. Plot mode uses the 240 references at `<runtime>/data/plot/`; the diagram runner does not use them. If preparing another diagram copy from a fresh external download:

```text
python <skill>/scripts/prepare_references.py --source <downloaded-MTP-root> --output <new-prepared-root>
python <skill>/scripts/prepare_reference_groups.py --dataset-dir <new-prepared-root> --output <new-prepared-root>/retrieval
```

The preparation command does not change its input download. It verifies all 298 reference images, fixes only the copied `ref_309` leading-U+200C path mismatch, records provenance, and preserves empty content in `ref_260`/`ref_305`. An existing destination is rejected. The test split is not a reference pool. Retained diagram/plot reference JSON and image bytes were preserved during deduplication; source snapshot JSON is under `data/sources/`.

- `auto`: use `--reference-groups <groups-root>` pointing to the prepared four groups of the original first 200 references. `grouped_retriever.py` selects six IDs from each group, then compares all 24 shortlisted full methodologies/captions to select ten. It preserves the original topic/visual-intent ranking criteria, but changes the selection count and JSON schema to `{"selected_diagrams": [...]}` for each of the five calls. This is an approved algorithm change from the original single 200-candidate request; equivalent ranking quality is not guaranteed. Random/none keep their original behavior.
- `random`: original random selection of ten from 298; use when requested or explicitly reporting a connection test. It does not establish relevance.
- `none`: explicitly omit references.

This project's groups are at `<runtime>/data/diagram/retrieval/`. Each contains at most 800,000 candidate characters. The adapter validates the dataset hash, full text, order and all 200 records before calling a model; it also bounds system-plus-user text to 1,000,000 characters. The host must preserve these texts and check its final envelope size. Character checks do not guarantee a model token limit. Missing/stale groups, invalid counts, duplicate IDs or IDs from another group fail; do not substitute random or truncate. All five selections and input IDs are retained in `retrieval.json` and `result.json.retrieval_audit`.

The group preparation command is offline and refuses an existing destination. It greedily partitions the first 200 complete records at 800,000 characters per group, requires four groups with at least six candidates each, and checks the full 24-finalist budget. On this dataset it reproduces group sizes 53/51/58/38 and the existing candidate text hashes. It does not download, truncate or summarize references. Pass the new retrieval folder to `--reference-groups`; do not overwrite the current dataset/groups during preparation.

Process the four group requests and the final request in separate model contexts, each using only that request's system instruction and complete user text. For each pending retrieval request run `python <skill>/scripts/respond_retrieval.py <request.json> --model gpt-6.1-sol --timeout 120`. This requires an existing ChatGPT Codex CLI login, reads the full request directly from disk, invokes an independent `codex exec --ephemeral`, and submits its response to the bridge. It uses no separate API key and records prompt, response, events, requested model and usage in the request's `codex-host/` folder. It refuses repeat submission. Do not accumulate all groups in one chat. This command handles retrieval only; PBInteract uses `respond_text.py` and the mandatory refine policy below.

For a readable request with a known ID, both text host commands submit explicit error responses for prompt preparation, missing CLI/login, process start errors and login timeouts, then exit with failure. The waiting runner can stop with its failure checkpoint immediately instead of waiting for its full timeout. Existing responses and prior host attempts are never overwritten; do not resubmit them.

The separate Codex text host needs access to its own local runtime (state database, temporary files and app-server) and its service connection, in addition to the coordinator's output folder. A passing local coordinator or `codex login status` does not prove `codex exec` can initialize. When the host requires an execution approval, describe the exact text-host command, request data and these side effects under the current host policy. Reuse the already agreed processing scope; do not add another research-data consent question for the same scope. Do not change global configuration, CODEX_HOME, credentials or the child's read-only/tool-isolation settings to evade restrictions.

An actual fatal permission error is recorded as `error_type=host_permission_denied`, `retryable=false`, with `failure_phase` in response.json and available host metadata. Preserve its logs and let the runner stop. Do not repeat the same failed request or start another figure run under unchanged permissions. Correct the concrete host permission condition through the host's approval mechanism before explicitly starting a fresh run. Generic database failures and nonfatal warnings alone are not sufficient evidence of permission denial. This classification provides diagnostics, not automatic elevation or guaranteed approval.

Planner receives the selected actual images and full example texts. View all images. If only text excerpts can be processed, disclose that difference; do not claim full-context equivalence. The runner requires ten distinct IDs from the active pool when references are enabled.

## Output location and delivery

Choose the output location before starting any generate, refine or select run:

1. Use the user's explicit destination when provided. Resolve a relative destination against the current conversation's actual working directory, not the skill location.
2. Otherwise, use `<conversation-workspace>/outputs/papersketch/<unique-run>/`. Obtain the workspace from the app-provided working-directory context. This applies both to a chosen project and to a projectless chat with an app-provided task directory.
3. If no usable workspace is available, ask for a destination. Do not invent a `Documents/Codex/<date>/<chat>` path or search unrelated conversations to guess it.

Capture the absolute conversation workspace before changing directories to run uv or locate the skill. Never infer it from `__file__`, the skill installation folder, this development repository, or the dataset root. A workspace pointing inside the installed skill or its assets/data is not a suitable inferred destination; ask instead. A user's explicit destination takes precedence. Resolve the data and skill roots separately from the output workspace.

Pass the chosen **absolute** directory as `--output`. The Python runner deliberately requires this argument; it cannot determine the active chat's workspace. Use a new, readable run name such as `diagram-01` or `plot-01`, choosing another name if it already exists. Every refinement/selection gets a new sibling run; retain the complete earlier run for continuation. Prepare input/feedback files in a separate task-local work directory: the runner requires its output directory to be absent or empty at startup. After it creates the run, keep prompts, exchange files and intermediate artifacts there or in the task-local work directory. Do not place them in skill source or reference data directories.

After the runner exits, verify the saved selection and its final review status. In the final answer:

- Show the selected `final.jpg` once as an inline image using its absolute local path. Intermediate candidates need not be repeated in the final answer.
- Provide a clickable Markdown link to that image; for Plot also link the actual `final.py`. Optionally link `description.txt` or `result.json` when helpful for editing/continuation. Do not imply that a PNG, SVG or editable illustration project exists unless it was actually produced.
- State the full absolute output directory in copyable text. Use absolute file links, not relative paths or `file://` URIs; wrap paths in angle brackets when they contain spaces.
- Briefly disclose `issues_remaining`, `review_failed`, `not_reviewed` or retained fallback results. A saved image alone does not establish review success. If the run failed, describe the failure and link only existing artifacts, without presenting an older image as a successful new result.

Example response shape (replace the placeholders with verified absolute paths):

```markdown
![Figure preview](<ABSOLUTE_PATH_TO_FINAL_JPG>)

[Open image](<ABSOLUTE_PATH_TO_FINAL_JPG>) · [Python code](<ABSOLUTE_PATH_TO_FINAL_PY>)

Saved folder: `ABSOLUTE_OUTPUT_DIRECTORY`
```

Omit the Python link for diagrams. The generated image tool's native save location is separate; copy its selected artifact into the chosen run before submitting it to the bridge and deliver the runner's saved final image.

## Initial generation

Save the methodology and desired caption as UTF-8 JSON: `{"content":"...", "visual_intent":"..."}`. When `additional_info` is omitted, `rounded_ratio` defaults to `21:9`, matching the upstream UI. Use `"additional_info":{"rounded_ratio":"16:9"}` for an explicit 16:9 run.

The diagram bridge adds the requested canvas ratio as an explicit constraint to every text request, including Planner, Stylist, Critic, PBInteract and final review, without changing the original system prompts or source content. The constraint takes precedence over conflicting canvas ratios invented by earlier descriptions. Prepared image prompts repeat that priority after the complete rendering description. This is an intentional adapter change; original agents and iteration order remain intact. Refinement inherits the saved ratio. Review context hashes include the ratio, so a verdict for another ratio cannot be reused. Always measure the returned image: these instructions do not guarantee exact tool output, and mismatches remain recorded without cropping, stretching or padding.

```text
python <skill>/scripts/run.py generate --input <input.json> --dataset-dir <prepared-root> --reference-groups <groups-root> --output <new-run> --retrieval auto --critic-rounds 3 --timeout 1200
```

The original `PaperVizProcessor` uses `demo_full`: `prepare_retrieval` → Planner → Stylist → Visualizer → Critic/re-render loop, with evaluation disabled. Visualizer renders **both Planner and Stylist descriptions separately**. Critic reviews the Stylist image first, then the prior revision. Preserve its render limits and selection, subject to the documented image-failure fallback. The adapter validates review responses and performs the read-only final review below; it does not add another render after the limit.

## Feedback and continuation

Read the saved result summary, then save the new feedback as UTF-8 text:

```text
python <skill>/scripts/run.py inspect --prior <previous-run>/result.json
python <skill>/scripts/run.py refine --prior <previous-run>/result.json --feedback-file <feedback.txt> --dataset-dir <prepared-root> --output <new-turn> --internal-rounds 2 --timeout 1200
```

The original PBInteract path is preserved:

1. Contextualize earlier requests and corresponding actual images once per feedback turn.
2. Critique the latest request, each earlier request separately, source content and presentation. The current description is withheld from this request.
3. Decide `YES`/`NO` in the same logical conversation. `NO` stops without image generation.
4. Only on `YES`, reveal the current description and rewrite it with concrete positive specifications.
5. Visualizer **generates a fresh image from the revised text**. This is not pixel editing; do not attach the previous figure to a text-only image request.
6. Further internal rounds examine the new image against all requirements and stop on convergence or the limit. The default internal limit is 1. This limits the iterative refinement passes; the runner's separate read-only final review adds no image generation.

For **every text request from `refine`**, run `python <skill>/scripts/respond_text.py <request.json> --model gpt-6.1-sol --timeout 180`. It starts a fresh Codex execution using only that request's system instruction, ordered explicit turns and attached images. Project instructions and stored memory injection are disabled for that invocation; no global configuration is changed. It rejects tool-using runs. Do not answer these requests in the active chat or add context from `inspect`, earlier Planner/Stylist work, or another request. The refine bridge requires independent-host request/response hashes; manual `respond.py --text-file` submissions are rejected.

Use a fresh execution for contextualization, critique, gating and rewrite separately, including every later internal round and feedback turn. The original Python includes the critique/model answers in gating/rewrite requests, so the intended logical conversation survives without carrying extra host memory. Only the rewrite request reveals the rendering description. The runner completes the assistant turn and retains original round indices, history keys, context, critique, earlier descriptions and images.

CLI transport serializes original user/model turns as ordered JSON inside one prompt and maps each image part to a numbered CLI attachment. These are not native API message roles or interleaved image placements. Preserve all text/parts/order and disclose this transport difference. Host markers/hashes are internal consistency checks, not authentication against malicious file modification.

## Selecting and branching

`inspect` lists `image_field`, description, current selection, feedback and `selectable`. `state.json` maps versions to viewable JPEGs. Selecting a version makes a new result without a model call:

```text
python <skill>/scripts/run.py select --prior <run>/result.json --image-field <selectable-image-field> --output <new-selection>
```

Selection is within the current completed turn, including its retained fallback image. To return to an earlier turn, pass **that turn's result.json** to `select` or `refine`. Do not combine an old image with later feedback history. This immutable branch preserves later result folders instead of deleting them as the original UI revert does. Re-selecting an internal render is an explicit added interface, not an automatic change to the processor's chosen result.

## Review validation and final verdict

The production runner wraps the preserved Critic/PBInteract agents with stage-specific response validation. Initial Critic and rewrite require both nonempty string fields `critic_suggestions` and `revised_description`, with consistent explicit no-change values. PBInteract context/critique require every field from their original dynamic schema; gating accepts exactly YES or NO. Valid JSON fences and explicit paired no-change wording are normalized; missing fields are never filled with a no-change verdict.

An invalid or empty model answer causes one additional **text-only** request with a new ID, the original conversation, the rejected answer and a format correction instruction. Maximum two answers per logical step; service the new request instead of editing an old response. Tool/transport failures are recorded separately and do not trigger this format retry. Normal-loop validation exhaustion stops with a failure checkpoint and preserves existing figures, rather than declaring success.

After the processor selects a valid figure, the runner finalizes `final_review` without calling Visualizer. It can reuse an existing valid review only when its image field, image-byte hash and source/user-requirement hash match the selected result. Otherwise initial generation uses the original Critic on a working copy; PBInteract finalization uses its all-requirements critique and YES/NO judgment, stopping **before rewrite**. Final requests require independent `respond_text.py` executions, even during initial generation. No review-only fields or proposed descriptions replace the selected image/description.

| `final_review.status` | Meaning and user-facing report |
|---|---|
| `passed` | Valid model review found no further issues; report review passed |
| `issues_remaining` | Valid review found issues; report them and retain the figure without further rendering |
| `review_failed` | Final review could not complete or validate; report failure and preserve the selected figure |
| `not_reviewed` | Older result or a different selected version has no matching verdict; do not inherit another image's pass |

Final-review failure after generation is saved as a viewable result with `completed_with_review_failure`; remaining issues use `completed_with_issues` unless image-failure status already applies. Image-generation status and final-review status remain separate. Save/inspect/CLI expose the verdict, evidence hashes and details; request outcomes and `requests/review_validation.json` preserve validation attempts. A selection change retains the prior verdict in history and marks the new version unreviewed. Model review is not a human quality certification. `--critic-rounds 0` disables iterative Critic renders, not the final read-only assessment.

## Parameters and saved files

| Option | Applies to | Default / meaning |
|---|---|---|
| `--input` | generate | Required UTF-8 JSON |
| `--prior` | inspect/select/refine | Required completed result |
| `--feedback-file` | refine | Required nonempty UTF-8 feedback |
| `--image-field` | select | Required selectable version key |
| `--dataset-dir` | generate/refine | Required prepared reference root |
| `--output` | generate/select/refine | Required new directory; earlier output is not overwritten |
| `--retrieval` | generate | `auto`; also `random`, `none` |
| `--reference-groups` | generate with auto | Required prepared four-group folder |
| `--critic-rounds` | generate | 3; integer >= 0 |
| `--internal-rounds` | refine | 1; integer >= 1 |
| `--timeout` | generate/refine | 1200 seconds per host request |

Each successful result is self-contained:

- `result.json`: original record, descriptions, feedback, critique, selected field and earlier images; image fields use relative `base64/<hash>` paths.
- `base64/`: original Interact content-addressed blob storage with deduplication. The adapter verifies each blob's filename against SHA-256 of its stored base64 text, including reused blobs at save time. Agents receive verified inline base64.
- `state.json`: image/description/version mapping, selection, parent path/hash, result hash and source-manifest hash.
- `images/`, `final.jpg`, `description.txt`: viewable intermediate JPEGs and the selected image/description.
- `run_config.json`: version 2 separates `requested_options` from `execution_policy`; CLI defaults describe requests, not proof that those operations ran.
- `requests/`: exact requests, responses, input-image sidecars and available independent-host logs.
- `retrieval.json`: auto strategy, dataset/group hashes, per-stage candidate IDs, selections and completion status; retained even before figure generation completes.

## Execution records

The runner saves `result.json.execution_record`, prior snapshots in `execution_history`, and the current record in `state.json.execution` and `inspect`/completion output. The record separates requested options, observed retrieval, parent input selection, current output selection and this run's bridge requests. Selection and feedback preserve retrieval origin/IDs without running retrieval again. A refine default of `--retrieval auto` is not evidence of a new auto search. New initial runs record the completed mode, IDs and applicable dataset/group hashes. Legacy origins remain `unverified`; do not infer a historical mode from an old CLI default. Parent file/image hashes are captured before selection or refinement changes the active figure. Prior folders are not required to read the saved snapshots.

`connector_name` is only a routing label. Per-request independent-host metadata is summarized only when its request hash matches; its model and reasoning fields are **requested**, not a verified internal model version or applied sampling. File submissions alone do not identify an actual model or tool. Record unavailable backend versions, sampling and tool identities as `unverified`, including imagegen identity when no tool evidence is available. `execution_policy.expected_image_tool` expresses intended use, not observed execution. Do not invent missing information or upgrade old records. Host hashes provide internal linkage, not signed authentication.

`bridge_request_counts` counts requests written by this Python run, including retries and failures; it is not a verified count of provider/model/tool invocations. Reused reviews, blocked image calls and selection can add zero requests. The current execution record also accompanies failure checkpoints. Recording these facts does not change agent prompts, reference selection or generation loops.

## Output aspect ratio

The bridge measures the returned image's pixel width/height and compares it with the original `image_config.aspect_ratio`. It records `image_ratio` in the successful attempt's `outcome.json` and image-generation history, and emits `PAPER_SKETCH_RATIO_WARNING` on mismatch. A mismatch remains a successful image response; do not submit `--error` or regenerate solely to obtain a matching ratio.

Saved state and `inspect` include `image_ratios` for every version and `selected_image_ratio` for the selected version; generate/select/refine CLI completion also reports the selected ratio. Preserve the requested ratio instead of replacing it with the actual value. `exact` means the pixel ratio is equal; `within_tolerance` means it differs by at most 0.5% relative error; `mismatch` exceeds that tolerance. Exact-match and error values are retained, so tolerance is not a claim of pixel-exact output. `not_requested` indicates no recorded requested ratio is available, especially for legacy records.

When the selected ratio mismatches, tell the user the requested ratio, actual dimensions/ratio, and that the image was left unchanged. For example: requested 21:9, received 1672×941 (about 16:9), ratio mismatch. This is a warning separate from image-generation failure. Do not crop, stretch, resize, or add padding. Existing original PNG-to-JPEG encoding remains; no aspect-ratio correction is applied. Prompt-only ratio guidance does not guarantee the built-in tool produces the requested canvas, and natural-language instructions inside the description are not automatically rewritten by this check.

Move/copy the **whole run folder**, not result.json alone. Resuming does not require parent folders: parent path/hash is provenance. For PaperSketch relative-blob results, `state.json` is required. Before inspect/select/refine, loading verifies the result hash, blob content hashes (also in nested history), selected field, each version's decoded-image hash and exported image, `final.jpg`, and its matching `description.txt`. Missing or replaced files fail before model requests; do not silently regenerate or substitute them. Saving verifies reused blobs and exports before publishing state.json.

The loader also accepts compatible earlier inline records and original absolute content-addressed blobs without state.json. Absolute blobs still undergo filename/content hash checks; metadata-free inline records have no stored identity anchor, so image decoding alone cannot establish their historical identity. This is an internal integrity check, not signed authentication against coordinated modification of the record, state and all images. Arbitrary upstream batch arrays/UI sessions remain unsupported.

## Image failures

Submit image tool errors with `python <skill>/scripts/respond.py <request.json> --error <reason> --error-type <type>`. Use `transient` only for an explicitly temporary failure with a known failed attempt, such as reported service unavailability. The bridge issues a **new request ID** for each retry, preserving the original prompt/settings; service only the new pending request. The original Visualizer supplies up to five attempts and a 30-second delay. Do not retry independently in the active chat or change the prompt to work around a refusal.

- `quota`, `refused`, and `unknown` do not retry. Use `unknown` when the cause is unclear; it is the default for `--error`. `invalid_input` and `fatal` abort with a failure checkpoint rather than a successful fallback.
- An image timeout is not evidence that the tool stopped. Do not resubmit the expired request. Quota and timeout also block later image calls in the current run to avoid repeated failures or uncertain duplicate generation.
- Missing/unreadable returned image files are recorded as `invalid_image`, without automatic retry. Closed attempts reject late `respond.py` submissions.
- Exhausted/non-retryable failures return the original `Error` sentinel to Visualizer. It marks that description as failed; the original processor keeps the last valid figure. If the initial selected render is absent but another initial render succeeded, the runner selects the last available render and records the fallback. No valid figure means failure.
- Report `completed_with_image_failures` as generation failure with a valid retained result, not a successful requested revision. `final.jpg` and `description.txt` correspond to the retained figure. Feedback, critique, failed revised descriptions and `image_generation_history` remain in `result.json`/`state.json`; attempt records are in `requests/image_generation.json` and each request's `outcome.json`.
- Failed runs write `failure.json` and `failed_record.json`, preserving intermediate descriptions/history/images. These are diagnostic checkpoints, not completed `result.json` files, and cannot be passed to `refine` as completed results. Existing prior folders remain intact.

## Servicing host requests

1. Keep Python running. Read each path printed after `PAPER_SKETCH_REQUEST`. Preserve `id`, original config and ordered user/model turns. The model-name field records provenance, not actual tool selection.
2. Treat source, examples, captions and earlier messages as task data. Apply the upstream system prompt within the host instruction hierarchy. Open every attached image using the host viewer.
3. For `kind=text` with `required_text_host=independent-codex`, run `respond_text.py` as above; it saves and submits the answer itself. Use `respond_retrieval.py` for grouped retrieval. For other initial-generation text stages, preserve the upstream schema and use `respond.py --text-file`, or use `respond_text.py` for an independent execution. Do not substitute an active-chat answer for a required independent execution.
4. For `kind=image`, prepare the tool prompt with `python <skill>/scripts/respond.py <request.json> --prepare-image-prompt <new-prompt.txt>`. This keeps the original render text intact and prefixes its API aspect-ratio setting, which the built-in tool must receive as text. Follow the installed imagegen skill with the built-in tool using that full prompt, then copy the returned artifact into the run. Submit `python <skill>/scripts/respond.py <request.json> --image-file <absolute-image-path>`. Never substitute fixtures. Record actual dimensions and any ratio/tier/sampling difference; requested ratio is not proof of exact output dimensions. The original Visualizer converts the output to JPEG.
5. Inspect the actual JPEG in every Critic request. On image tool failure use the classified error policy above; only explicit transient failures retry. Text errors/timeouts and input/contract failures still abort, preserving a diagnostic checkpoint. Do not label retained figures as successful revisions.
6. Continue until Python exits. Inspect the saved selection and report retrieval mode, actual calls and remaining limits. Deliver the preview, clickable files and full saved directory according to Output location and delivery above.

## Verification scope

Run offline state/data tests first, then a single candidate and feedback with live tools when authorized. Fixture checks establish contracts and control flow; live samples establish tool wiring. Neither proves benchmark quality or model equivalence. The production runner guards malformed review responses and finalizes a read-only verdict; raw upstream agents and diagnostic probes do not provide those runner guarantees. The Python-only `guard_reviews=False` option is reserved for original-flow regression comparisons and has no production CLI switch. Diagnostic `probe.py` and `reference_probe.py` cover narrower subsets and do not replace the full runner.

To check the actual five auto requests without image generation, run `reference_probe.py --dataset-dir <prepared-root> --reference-groups <groups-root> --input <input.json> --exchange-dir <new-run> --retrieval auto --retrieval-only`. Service each request with an independent Codex context. This stops after retrieval; omitting `--retrieval-only` also calls the original Planner.
