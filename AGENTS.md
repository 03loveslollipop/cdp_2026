# Repository Guidelines

## Start Here

Read `PROGRESS.md` before continuing model-training work. It records the checkpoint,
completed validation, benchmark results, and the next requested feature. This directory
is the Git repository root; remote `cdp_2026` points to `03loveslollipop/cdp_2026`.

## Structure and Commands

`etl_scripts/src/ft_engineering.py` owns shared preparation. Model orchestration lives
in `model_training_evaluation.py`; `torch_classifier.py` and `heuristic_model.py` contain
custom estimators. Rules belong in `config.json`; search settings belong in
`model_training_config.json`. Tests live in `tests/`; documentation and published
aggregate figures live in `docs/`.

```bash
python -m pip install -r requirements.txt -r requirements-training.txt
python -m pytest -q tests
python -m etl_scripts.src.model_training_evaluation --smoke --output-dir runs/smoke_new
```

Use four-space indentation, descriptive snake_case names, and short imperative commits.
Keep changes scoped and follow `CONTRIBUTING.md`. Preserve existing user edits.

## Modelling Invariants

- Preserve the chronological 70/30 raw-data split and timestamp groups. Fit preparation,
  encoding, scaling, weights, calibration, and thresholds on training partitions only.
- Never use `puntaje`, its derivatives, the target, or metadata as predictors. Retain
  configured missingness indicators and validation flags; do not silently remove rows.
- Default is `Pago_atiempo=0`. Public probabilities follow `[P(default), P(on-time)]`.
  Reuse `build_model` and `summarize_classification` for every model family.
- Select using default-class F1, temporal/seed consistency, and CPU inference cost.
  Never use the final holdout to select trials, thresholds, or the winner.

## Development and Deployment

Tracked training, tests, CI, and deployment are CPU-only. CUDA experimentation belongs
exclusively in the ignored `.local_cuda_training/` copy; do not push CUDA-specific code
or tests. Experimental artifacts must load and predict in a separate CPU-only
environment before they are considered for deployment.

Budget-controlled TPE search is available as an opt-in alternative to the grid
baseline. Keep trial counts and time budgets configurable and reported; see
`PROGRESS.md`.

## Artifacts and Handoff

Keep model binaries, optimization databases, environments, and record-level predictions
out of Git. Publish only aggregate reports/figures. Update `PROGRESS.md` with commands,
results, limitations, and outstanding work. Do not claim GPU validation without running it.
