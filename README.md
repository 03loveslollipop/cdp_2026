# Credit & Payment Behaviour — exploratory data analysis

The predictive workflow now includes [model training and evaluation](
docs/model_training.md): eleven model families and references, temporal validation,
default-class F1 selection, comparative graphs, and a portable fitted model object.
The clean [training notebook](etl_scripts/src/development/model_training.ipynb) provides
an interactive CPU-oriented entry point over that same tested workflow.

A portfolio of **10,763 Colombian consumer loans** disbursed between November 2024 and
April 2026, with a binary outcome for whether each loan was repaid on time. The default
rate is **4.75%**, roughly one loan in twenty.

The file arrives **without a data dictionary**, so the first job was not modelling but
establishing what each column measures, which ones are trustworthy, and which ones do not
mean what their names suggest. That turned out to be the substance of the work: the most
predictive column in the file cannot be used, one column is denominated in units its name
does not declare, and the signals that do survive are individually weak.

📄 **[`ResultsReport.pdf`](ResultsReport.pdf)** — the full written report
🖼 **[`ResultsPresentation.pptx`](ResultsPresentation.pptx)** — the results deck

---

## 1 · `puntaje` is target leakage

The internal score `puntaje` correlates with the outcome at **r₍pb₎ = 0.923**, where no
other column in the file exceeds |ρ| = 0.11. That disproportion is a reason to audit it
rather than celebrate it.

![Distribution of puntaje by outcome](docs/figures/01_leakage_score_distribution.png)

The two outcome classes **never touch**. The highest value among defaulted loans is 62.67
and the lowest among loans repaid on time is 63.81, leaving an empty 1.14-point corridor
that contains no loan of either class. Any threshold inside it reproduces the label for
100% of the 10,763 rows — it is not one lucky cut but a corridor of equally perfect ones.
On top of that, **87% of the portfolio sits on a single repeated value** and every one of
those loans was repaid.

The regulatory context explains how a column like this comes to exist. Colombian
supervised entities must assess credit risk both at origination and across the life of the
loan, so a warehouse routinely holds more than one score per loan, and a behavioural score
is by construction a function of the outcome.

## 2 · What a score that does *not* leak looks like

The same chart for `puntaje_datacredito`, the DataCrédito Experian bureau score on its
official 150–950 scale:

![Distribution of the bureau score by outcome](docs/figures/19_bureau_score_by_outcome.png)

Here the classes **overlap almost entirely** — defaults spread from 287 to 922, a range
containing 99.7% of all scored loans. The defaulted distribution sits slightly to the
left, which is where its ρ = +0.091 against the outcome comes from, but it is *contained
within* the repaid distribution rather than separated from it.

That contrast generalises beyond this dataset: **a score that predicts an outcome produces
a gradient; a score that already knows it produces a wall.**

## 3 · The two scores do not measure the same thing

![puntaje against puntaje_datacredito](docs/figures/18_two_scores_against_each_other.png)

The dashed line is where clients would fall if both instruments ranked the same risk across
their declared scales. It is anchored on those scales rather than fitted to the sample, so
it is a reference and not a model. No part of the cloud follows it: the two scores
correlate at only **ρ = 0.118**. Among the 1,777 clients whose bureau score sits between
790 and 810 — practically identical risk according to the bureau — `puntaje` takes every
value between −21.9 and 95.2.

## 4 · A column denominated in units its name does not declare

![Unit proof](docs/figures/10_units_thousands_of_pesos.png)

`saldo_total` has a median of 16,178 against a median declared salary of 3,000,000 COP.
Read as pesos, the typical client — who holds five open obligations — would owe half a
percent of one month's pay.

The proof is internal. Of the 636 clients with exactly one open obligation, **402 also
carry a positive balance** — their entire bureau balance must be the loan just granted
them. As delivered, `capital_prestado / saldo_total` has a median of 1,338; divided by a
thousand it becomes 1.34, leaving the outstanding balance at 74.7% of the original
principal, which is what a part-amortised loan should look like.

| Quantity | As delivered | Corrected |
|---|---|---|
| Median total bureau debt | 16,178 COP | **16.2 M COP** |
| …as a multiple of monthly salary | 0.005× | **5.4×** |
| Median arrears when present | 236 COP | **236,000 COP** |

That last row is why it matters: **236 pesos reads as a rounding residual, 236,000 reads as
a genuine overdue amount.** The error produces no missing values and violates no range
rule — it is only detectable by comparing magnitudes against what the domain expects.

## 5 · Linear correlation alone would have discarded most of the file

| Variable pair | *r* (linear) | *ρ* (rank) | Gap |
|---|---|---|---|
| `salario_cliente` × `saldo_total` | 0.005 | 0.445 | 0.441 |
| `total_otros_prestamos` × `saldo_total` | 0.083 | 0.444 | 0.361 |
| `salario_cliente` × `cuota_pactada` | 0.052 | 0.393 | 0.341 |

Eleven of the twelve largest gaps share this shape. The cause is a handful of declared
salaries up to 22,000 million COP — unit errors, not wealthy clients — and Pearson, being
computed on squared deviations, lets a dozen outliers dominate the coefficient entirely.

## 6 · The signals that survive

**Arrears already on the bureau file.** Clients carrying an overdue balance elsewhere
default at **36.4% against 4.6%** — 7.7× the portfolio rate. It needs no model: the
information is already on file at application time.

![Default rate by prior arrears](docs/figures/13_arrears_default_rate.png)

It fires on only 55 loans (0.51% of the book, 3.91% of all defaults), and that rarity is
itself informative — negative bureau data persists for years under Ley 2157, so the
originator is evidently *already* screening on this field.

**Inquiry intensity.** Bureau inquiries per account actually opened: clients generating
inquiries that are not converting into approvals are being refused credit elsewhere.

![Default rate by inquiry intensity decile](docs/figures/15_inquiry_intensity_deciles.png)

The top two deciles default at **7.8% against 2.8%** in the bottom three. DataCrédito
states that inquiry footprints do not feed its score, which is why this variable carries
information the bureau score cannot — the two correlate at only ρ = −0.18.

## 7 · What the clean signals reach when combined

![Review queue capture curve](docs/figures/17_review_queue_capture_curve.png)

Four leakage-free signals converted to percentiles and averaged with equal weights separate
the book from 2.5% to 11.9%. Each client is scored on whatever components they actually
have; filling the gaps with a neutral value would be an imputation, and would have touched
2,948 of the 10,763 rows. In operational terms, a manual review queue holding **2,153 of
the 10,763 applications reaches 38% of all defaults** — about twice what random review
would achieve.

**This is not a model.** Four variables with equal weights, measured on the same sample
that suggested them, with no train/test split and no calibration. The figure establishes
that the opportunity is large enough to justify building a validated model; it is not a
forecast.

---

## Limitations

- **Population.** The median client holds five open obligations against two or fewer for
  62% of the Colombian bureau population, and the median bureau score is 792. This is a
  pre-screened, credit-experienced segment, so the weakness of the surviving signals may be
  a consequence of that filter rather than a property of the variables.
- **Incomplete bureau sectors.** The three sector columns sum to less than the account
  total in 71% of rows, median shortfall two accounts. The missing one is almost certainly
  telecommunications and fintech.
- **Label definition.** How `Pago_atiempo` is defined, and when it becomes final, is
  unknown. Whether the recent cohorts are usable depends on the answer.

## Repository

```text
PYTHON_ETL/
├── etl_scripts/src/
│   ├── development/eda.ipynb   the analysis, end to end
│   ├── config.json             every threshold, rule and semantic decision
│   ├── ft_engineering.py       tested cleaning and feature pipeline
│   └── heuristic_model.py      explainable EDA-based risk benchmark
├── tests/                      pytest pipeline and model checks
├── docs/figures/               figures used in this README
├── dataset.csv                 source extract the analysis is built on
├── ResultsReport.pdf           the written report
├── ResultsPresentation.pptx    the results deck
├── requirements.txt            pinned dependencies
└── setup.sh / setup.ps1        create .venv and install
```

```bash
./setup.sh                       # or  .\setup.ps1  on Windows
.venv/bin/python -m jupyter lab etl_scripts/src/development/eda.ipynb
```

The predictive workflow creates a chronological 70/30 split, fits preprocessing on the
older training rows, writes predictors and targets separately, and saves its fitted
medians for later validation or live data:

```bash
python -m etl_scripts.src.ft_engineering split-fit \
  --input dataset.csv \
  --train-output train_predictors.csv \
  --test-output test_predictors.csv \
  --train-target-output train_target.csv \
  --test-target-output test_target.csv \
  --train-metadata-output train_metadata.csv \
  --test-metadata-output test_metadata.csv \
  --artifact preparation.joblib \
  --diagnostics-output split_report.json

python -m etl_scripts.src.ft_engineering transform \
  --input validation.csv \
  --output validation_predictors.csv \
  --metadata-output validation_metadata.csv \
  --artifact preparation.joblib

python -m pytest -q tests/test_data_preparation.py
```

The split sorts raw rows by `fecha_prestamo`, assigns the oldest 70% to train and newest
30% to test, and keeps identical timestamps in one partition. On this extract that is
7,534 train rows through 26 May 2025 13:31 and 3,229 test rows beginning at 13:32. The
date is returned as metadata and never used as a predictor. Use the separate `fit` command
when an upstream process already owns the split.

The pipeline enforces an explicit 19-column input contract, applies the notebook's null,
type, sentinel, and unit rules, and builds 24 calculated variables.
It converts hard-invalid ages and bureau scores to missing values, retains plausible
extremes with diagnostic warnings, then learns numeric medians and the categorical
`Missing` value from training rows only. Each of the 42 prepared values receives a stable
missingness indicator, producing 84 columns before model-specific encoding or scaling.

The target, unexpected columns, `puntaje`, `saldo_mora_codeudor`, raw
`saldo_principal`, and all date features are excluded. The 1,000x bureau-balance scale and
availability of non-leaking bureau fields at application time remain assumptions that
must be confirmed before deployment.

### Heuristic benchmark

`CreditRiskHeuristicClassifier` is a scikit-learn-compatible, explainable baseline over
four EDA signals: inquiry intensity, bureau score, the gap between bureau and declared
income, and existing arrears. It learns percentile references and probability calibration
only from the training partition; missing components are omitted from each row's weighted
average. Fit it directly on the shared pipeline output:

```python
from etl_scripts.src.heuristic_model import CreditRiskHeuristicClassifier

model = CreditRiskHeuristicClassifier(review_fraction=0.20)
model.fit(split.train.predictors, split.train.target)
default_probability = model.predict_proba(split.test.predictors)[:, 0]
review_reasons = model.explain(split.test.predictors)
```

Class `0` means default and class `1` means on-time payment. `predict_review` flags the
highest-risk training-defined segment; `explain` exposes component scores and missingness.
On the current chronological holdout, the heuristic reaches ROC-AUC 0.624 and captures
26.9% of defaults in a 19.2% review queue. Treat it as a transparent benchmark, not a
production approval or denial policy; thresholds and calibration require monitoring and
business validation.

**No threshold is hard-coded in the notebook.** `config.json` carries the validation rules,
the `unit_scale` block behind finding 4, the sentinel values that stand for "no
information", the leakage declaration, and the published Colombian reference values the
rules were checked against. Changing a threshold means editing that file.

## Notes for whoever picks this up

- The target is imbalanced at 4.75% positives. Use PR-AUC or recall at fixed precision —
  predicting the majority class already scores 95.25% accuracy.
- **Split by `fecha_prestamo`, not at random.** Recent cohorts have not had time to mature.
- **Exclude `puntaje` and everything derived from it.** Leakage propagates: a rule-violation
  counter built as an ordinary derived feature scored ρ = −0.287 until it turned out one of
  the rules bounds `puntaje` and every row violating it is a default. Rebuilt from clean
  rules it falls to −0.008. Section 5.1 of the notebook now asserts that no leakage column
  reaches the modelling frame rather than merely printing that it was excluded.
- `saldo_total` and `saldo_principal` correlate at ρ = 0.946 and are identical in 84% of
  rows; keep one plus the interest difference.
- **Nothing is imputed in the EDA.** The notebook turns disguised unknowns *into* nulls — null tokens,
  the not-scored sentinel, the 58 trend labels that arrived as numbers — and then leaves
  them null. The predictive pipeline performs its documented median/`Missing` imputation
  only after a training split and preserves an indicator for every missing source or
  calculated value. This keeps the EDA descriptive while giving downstream estimators a
  complete, finite input frame.
