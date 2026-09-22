# AI Shipping Auditor

A hybrid ML + LLM pipeline that classifies inbound logistics email and automatically cross-checks Shipping Instruction (SI) vs draft Bill of Lading (BL) documents — built for the SDOC Hackathon, Document Intelligence track.

Runs completely free by default (deterministic rules + a local scikit-learn model). An LLM call is used only as an optional, confidence-gated fallback for the emails the local stages genuinely can't resolve.

---

## Table of contents

- [Problem](#problem)
- [Solution](#solution)
- [Tech stack](#tech-stack)
- [Architecture](#architecture)
- [Results / success metrics](#results--success-metrics)
- [Setup](#setup)
- [Usage](#usage)
- [Problem–solution alignment](#problemsolution-alignment)
- [AI and cloud infrastructure integration](#ai-and-cloud-infrastructure-integration)
- [User feedback / testing](#user-feedback--testing)
- [Coding challenges](#coding-challenges)
- [Scalability plans](#scalability-plans)
- [Repository structure](#repository-structure)
- [License](#license)

---

## Problem

Shipping and logistics teams triage hundreds of inbound emails a day across five intents — BL comparisons, SI requests, invoice queries, general operations, and spam. For every BL comparison request, someone has to manually cross-reference **7 canonical fields** (shipper, consignee, weight, port, container count, etc.) between the Shipping Instruction and the draft Bill of Lading, using labels that are rarely identical between the two documents. A missed mismatch on a field like consignee or weight can delay a vessel or trigger a costly claim. This is slow, repetitive, and error-prone at scale.

## Solution

AI Shipping Auditor automates the full pipeline: classify the email's intent, extract the relevant document fields, and verify them against each other — escalating to a human (or an LLM) only when it's genuinely unsure, rather than guessing.

## Tech stack

**Classification**
- `scikit-learn` — TF-IDF (word n-grams + character n-grams, on subject and body separately) feeding a `LogisticRegression` classifier
- Structural/rule-based features — attachment presence, sender domain, reply detection
- `OpenRouter` (Llama 3.3 70B) — optional LLM fallback, used only on low-confidence cases
- Deterministic keyword-rule fallback — used automatically when no LLM API key is configured, so the system always has a free path

**Document parsing**
- `pdfplumber` — label/value extraction from PDF attachments
- `python-docx` — paragraph and table extraction from Word attachments
- `openpyxl` / `pandas` — spreadsheet attachments

**Comparison & matching**
- Fuzzy label matching — word overlap, acronym matching, and `difflib.SequenceMatcher` character similarity, to line up fields that are named differently across documents (e.g. "Port of Loading" vs "POL" vs "Load Port")
- Unit normalization — weights (KG/MT) and container counts, before exact comparison

**App & delivery**
- `Streamlit` — dashboard (audit log, document diff inspector, live single-email tester, accuracy-vs-ground-truth view, supervisor portal)
- `FastAPI` / Docker — evaluation server
- `joblib` — trained model persistence

## Architecture

A cost-ordered cascade: every email is handled by the **cheapest stage** that can decide it confidently, so paid inference is the exception, not the default path.

```
Email in
   │
   ▼
1. Attachment rule        →  _SI / _BL file pair present?           free · instant
   │ (no match)
   ▼
2. Local ML model         →  TF-IDF + logistic regression,          free · ~ms
   │ (confidence < 45%)       confidence ≥ 45% required
   ▼
3. LLM (OpenRouter)        →  low-confidence cases only,             paid · seconds
   │ (no API key set)          if a key is configured
   ▼
4. Keyword fallback        →  deterministic rules                    free · instant
```

For `BL_COMPARISON` emails, the matched SI and BL attachments are parsed, fields are fuzzy-matched to 7 canonical labels, values are normalized, and each field is marked `MATCHED`, `NOT_MATCHED`, or `REVIEW_NEEDED`. Emails that can't be resolved safely (unreadable scan, missing attachment, missing value, wrong document type) are escalated to `NEEDS_REVIEW` instead of guessed.

## Results / success metrics

Scored against the official hackathon metric:
`FINAL SCORE = 0.3 × Stage-1 macro-F1 + 0.2 × Stage-3 defect-F1 + 0.5 × end-to-end defect recovery`

| Test set | Final score | Notes |
|---|---|---|
| Original hackathon dataset (keyword-only baseline) | 0.9825 | For comparison |
| Original hackathon dataset (this hybrid pipeline) | **1.0000** | Perfect on seen data |
| Independently-worded, unseen dataset | **0.9133** | New wording never trained on |
| Hand-built hard/complex cases | **0.6838** | Non-English, phishing, forwarded threads, negations, multi-intent |

We deliberately built a **second, independently-worded dataset** (different templates, senders, phrasing) to avoid grading ourselves on memorized templates — the 1.0 score on the original data does not imply real-world generalization by itself, and the unseen/complex numbers above are the honest read.

**Cost efficiency:** on unseen data, **83–87% of emails are resolved confidently by the free local stages alone** — only about 1 in 5 emails ever reaches the paid LLM step. Stage 3 (SI vs BL field comparison) held perfect precision and recall across every test split.

## Setup

```bash
git clone <this-repo>
cd shipping_verifier
pip install -r requirements.txt
```

Optional — enable the LLM fallback (skips automatically if unset):

```bash
export OPENROUTER_API_KEY="your-key-here"
```

Train / retrain the local model:

```bash
python train_model.py --bundle <path-to-email-bundle> --labels ground_truth.json --out model.joblib
```

## Usage

Run the batch pipeline:

```bash
python main.py --bundle <path-to-email-bundle>
```

Launch the dashboard:

```bash
streamlit run app.py
```

The dashboard has five tabs: **Audit Summary & Logs** (KPIs, filters, decision source/confidence), **Document Diff Inspector** (field-level SI vs BL comparison), **Live Tester** (paste or upload a single email to run through the full pipeline), **Accuracy vs Ground Truth** (upload any `ground_truth.json` to get the official tester metrics inline), and **Supervisor Portal** (human-in-the-loop review queue).

## Problem–solution alignment

The core problem is manual, error-prone, field-by-field document reconciliation at email scale. The solution addresses this directly and only this: it does not try to replace human judgment on ambiguous cases, it routes them to `NEEDS_REVIEW` or an optional LLM/human step. Every design decision — the cascade order, the confidence threshold, the fuzzy label matching — traces back to reducing manual triage time without introducing silent misclassification risk on a domain (shipping documents) where a wrong "match" is more costly than a flagged review.

## AI and cloud infrastructure integration

- **Local ML** (scikit-learn) does the bulk of classification work with no external dependency or per-call cost.
- **LLM integration** (OpenRouter, Llama 3.3 70B) is wired in as an explicit, optional, confidence-gated fallback rather than the primary classifier — it is only invoked when the local model's confidence falls below threshold, keeping inference costs proportional to genuine difficulty rather than volume.
- **Containerization**: the evaluation server runs via FastAPI + Docker, so grading/scoring is reproducible and isolated from the local dev environment.
- The architecture is provider-agnostic at the LLM layer — swapping OpenRouter for another provider only touches one module (`llm_classifier.py`).

## User feedback / testing

- Automated testing: `streamlit.testing.v1.AppTest` for headless dashboard smoke tests, plus `StratifiedKFold` / `GroupKFold` cross-validation (grouping near-duplicate templated emails to prevent train/test leakage).
- Hand-written "paraphrase" emails used to sanity-check true generalization vs template memorization during development.
- A dedicated, independently-worded dataset (`train_varied` / `unseen_test` / `complex_llm` splits) built specifically to expose and quantify the gap between seen-data accuracy and real-world accuracy, rather than relying on the original dataset's score alone.
- The dashboard's **Live Tester** tab exists specifically so a reviewer (human-in-the-loop) can paste in an arbitrary email and immediately see which stage decided it, at what confidence, and why — surfacing model behavior for ongoing feedback rather than treating it as a black box.

## Coding challenges

- **Templated data hides real accuracy** — scoring against the same generated dataset used for training produced a misleading 1.00. Solved by building a separate, differently-worded dataset to get an honest read.
- **Sender-domain features overfit** — the model learned to treat unfamiliar domains (e.g. `gmail.com`) as a spam signal. Removing sender-domain features improved unseen-data accuracy from ~72% to ~82%.
- **Field label matching across formats** — SI and BL documents label the same field differently (e.g. "Port of Loading" vs "POL" vs "Load Port"). Solved with acronym-aware fuzzy scoring instead of a fixed alias list.
- **Keeping the LLM optional** — the system had to run fully free with no API key configured, and upgrade gracefully once one is added, without the keyword fallback ever becoming the primary path in a configured environment.

## Scalability plans

- **Harden the classifier** (now → +1 month): collect real, anonymized inbox data to retrain beyond synthetic templates; add an active-learning loop that logs every low-confidence + LLM decision for retraining.
- **Extend document coverage** (+1 → +3 months): OCR fallback for scanned/image-only attachments; move from alias-list field matching to embedding-based semantic matching.
- **Production readiness** (+3 months →): wire the human-in-the-loop review queue to a real ticketing system; add SLA dashboards, an audit trail, and role-based access for the supervisor portal.

## Repository structure

```
shipping_verifier/
├── main.py                # Batch pipeline entry point
├── classifier.py          # Hybrid classifier (rule → ML → LLM → keyword fallback)
├── llm_classifier.py       # OpenRouter-based LLM fallback
├── ml_pipeline.py          # TF-IDF + logistic regression classifier
├── hackathonprototype.py   # Stage 3 SI/BL comparison engine
├── train_model.py          # Model training CLI
├── model.joblib            # Trained model artifact
├── app.py                  # Streamlit dashboard
├── requirements.txt
└── varied_dataset/          # Independently-worded train/unseen/complex test splits
```

# Repository clone URL
https://github.com/gitenvy/averis_hackaton.git
