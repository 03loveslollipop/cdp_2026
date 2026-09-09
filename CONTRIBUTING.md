# Contributing to Credit Payment EDA

Thank you for improving this project. Contributions must keep the exploratory analysis,
data-preparation pipeline, tests, and published findings reproducible and consistent.

This workflow is adapted from the
[OpenCROW contribution guide](https://github.com/02loveslollipop/OpenCROW/blob/main/CONTRIBUTING.md).

## Contribution Workflow

### 1. Establish Scope

For substantial changes, open an issue describing the problem, proposed approach, affected
files, and analytical or business risk. Keep each issue and pull request focused on one
concern. State whether the change affects the dataset schema, validation rules, derived
features, reported statistics, or generated artifacts.

### 2. Implement

- Branch from the latest target branch and use a descriptive name such as
  `feat/inquiry-features` or `fix/balance-units`.
- Put thresholds, sentinels, column semantics, and unit rules in
  `etl_scripts/src/config.json`; do not duplicate them in code.
- Keep reusable preparation logic in `etl_scripts/src/ft_engineering.py` and exploratory
  reasoning in `etl_scripts/src/development/eda.ipynb`.
- Do not silently impute missing values, repair outliers, or drop records. Such decisions
  require explicit justification and validation.
- Never expose `puntaje` or any feature derived from it to the modelling frame. It is a
  documented target-leakage field.
- Update source files before committing regenerated PNG, PDF, or PPTX artifacts.

### 3. Test

Every pipeline change must include or update tests under `tests/`. Cover expected values,
null behavior, boundary inputs, invalid schemas, leakage exclusion, and operation on the
complete source extract where relevant. A bug fix must include a regression test that
would fail before the fix.

Run from `PYTHON_ETL/`:

```bash
python -m pytest -q tests
python -m py_compile etl_scripts/src/ft_engineering.py
```

For notebook or reporting changes, restart the notebook kernel, run every cell, and check
that figures and statistics agree with `README.md` and the published report.

### 4. Submit a Pull Request

Use a short imperative commit subject and keep unrelated formatting out of the diff. The
pull request must include:

- the problem and implemented solution;
- affected transformations, features, and artifacts;
- exact validation commands and results;
- operating system, architecture, Python version, and key dependency versions;
- before/after images when plots or slides change;
- linked issues and known limitations.

Do not commit credentials, virtual environments, caches, model binaries, or datasets that
have not been approved for version control.
