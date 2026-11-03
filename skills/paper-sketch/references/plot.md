# Statistical Plots

Use this mode for numerical charts, such as bar charts, line charts, scatter plots and heatmaps. Architecture illustrations use the diagram mode. Plot mode does not invoke imagegen or PBInteract.

## Source and preserved behavior

`assets/paperbanana_plot/` contains the PaperBanana implementation at `f1da3db8d5f4c3add947dfd3ddd93dddd3394dc3`. `SOURCE_MANIFEST.json` records source/vendored hashes and every source replacement; keep the Apache-2.0 license and copyright headers. The original Plot system prompts, style guide, Matplotlib worker and full pipeline are retained. Changes connect the dataset path, module namespace, and local execution hook. The existing Diagram implementation is separate.

The original sequence is Retriever → Planner → Stylist → Visualizer → Critic/re-render loop. Visualizer renders both the Planner and Stylist descriptions, then any requested revisions. Critic starts from the Stylist plot, rewrites the whole description and stops on `No changes needed.` or the configured limit. Failed revisions keep the previous valid plot. PaperSketch adds schema validation and a read-only final review; this final review never generates more code or images.

## Input and invocation

Save UTF-8 JSON with `content` containing the actual numerical data and `visual_intent` describing the chart. Dictionary/list and textual table data follow the upstream contract; a file path alone is not file ingestion. Read a user-supplied file locally and supply its actual relevant data. Reference examples guide presentation; they do not replace the user's values. Do not fabricate missing measurements.

```json
{"content":{"A":10,"B":15,"C":12},"visual_intent":"Vertical bar chart; show values, y-axis Value starting at zero, no figure title."}
```

```text
python <skill>/scripts/run.py generate --task plot --input <input.json> --dataset-dir <project>/data/plot --output <new-run> --retrieval auto --critic-rounds 3 --plot-timeout 30 --timeout 1200
```

`--task` defaults to `diagram`; specify `plot` explicitly. Use a fresh output directory. Negative critic limits and nonpositive execution timeouts are rejected. `--reference-groups` is not used for plots.

## Retrieval and host requests

- `auto`: the original Retriever compares the entire Plot reference pool (240 here) in one request and selects ten `top10_plots` IDs. This is not the diagram first-200/four-group algorithm. Validate host envelope size without truncating or silently changing to random.
- `random`: original random ten from the whole pool; disclose the mode.
- `none`: no reference examples.

The adapter checks unique IDs, image paths and readable reference images. Missing/invalid data and invalid selection results fail explicitly instead of claiming reference retrieval succeeded. Planner receives ten actual reference images with their full raw data and visual intent. The dataset `ref.json` is not modified or copied by a generation run.

Every emitted `PAPER_SKETCH_REQUEST <request.json>` is a text request. Use:

```text
python <skill>/scripts/respond_text.py <request.json> --model gpt-6.1-sol --timeout 180
```

Use this for Retriever, Planner, Stylist, code generation and Critic. Each runs in an independent context containing only its explicit upstream inputs. The existing ChatGPT Codex login is required; no provider API keys are used. Do not route Plot retrieval to `respond_retrieval.py`, which is specific to the diagram grouped schema.

The Visualizer response is Python code. Use only data and generated code authorized for the model call and local execution. Inspect the code when its inputs/provenance are untrusted, and use an OS sandbox for untrusted execution. Do not introduce network/file access unrelated to the chart. The original renderer uses Python `exec`; a separate process and timeout are not a security sandbox.

## Local rendering, failures and saved outputs

The upstream `execute_plot_code_worker` extracts fenced Python, selects Matplotlib Agg, executes the code and saves the active figure as a 300-DPI JPEG with `bbox_inches='tight'`. It must leave a Matplotlib figure open. PaperSketch invokes that worker in a fresh process with a per-execution timeout and a run-local working/cache directory. It records stdout/stderr, renderer versions, code and image hashes. Invalid code, no figure, worker failure and timeout remain recorded failures; they are not silently successful charts.

Before execution, `plot_code.py` corrects one diagnosed code pattern: adjacent `collection.set_clip_path(bar)` followed by `axes.add_collection(collection)` with the same named collection and named clip target. It moves the clip call after insertion so Matplotlib does not replace the bar clipping with the axes clipping. Other code is preserved; unsupported patterns and syntax errors are left for normal execution/error handling. This is an intentional adapter change, not an upstream model capability or a general code debugger. Raw model responses remain in `*_code` and response.txt; actual executed code is recorded separately in `*_executed_code` and code.py. Repairs and both hashes are logged, and exported final.py/version code use the actual executed code. Loading older results does not silently change their code or images.

`--plot-timeout` limits each rendering attempt, not the whole run. The upstream Visualizer may retry a missing initial render when processing a later revision. The Critic-round limit still bounds the generation loop. If no valid image exists the run writes a failure checkpoint; it cannot be resumed as a completed result. If a revision fails, the last valid image is retained and failures remain visible. Imagegen retry policy is not applied to Matplotlib jobs.

The diagram default 21:9 is not applied to plots. The generated code controls `figsize`; tight bounding boxes can change final pixel proportions. An explicit `additional_info.rounded_ratio` is recorded and checked without cropping, stretching or padding. No PDF/SVG export is claimed by this mode.

Saved outputs include `final.jpg`, executable extracted `final.py`, `description.txt`, each successful image/code version, `result.json`, `state.json`, `retrieval.json`, `run_config.json`, host requests and `plot_execution.json`. Per-attempt files are under `plot-execution/`. Original raw code responses, including failed ones, remain in the record/attempt folders. Image and code exports are checked against the saved record on load.

Text host preflight failures with a known request ID also write an error response before exiting, so CLI/login/prompt failures reach the runner without a full bridge timeout. They are failures, not successful plots or permission to switch providers.

```text
python <skill>/scripts/run.py inspect --prior <run>/result.json
python <skill>/scripts/run.py select --prior <run>/result.json --image-field <version-field> --output <new-selection>
```

Selection exports the matching image, description and code; it invalidates a verdict for another selected image. `refine` rejects a Plot result, even if `--task plot` was omitted. PBInteract is only connected for diagrams. To make a new Plot request, run `generate --task plot` again with the desired data and visual intent.

## Verification boundaries

Use offline fixtures to verify full-pool selection, ten image/text attachments, source prompts, render order, early exit, bounded revisions, malformed responses, renderer failures, timeout, save/load and version selection. Check numerical data in the generated code and rendered Matplotlib objects for known fixtures; an image-only Critic verdict does not prove data fidelity. Real Codex samples validate wiring and observed output only, not PaperBanana performance equivalence.
