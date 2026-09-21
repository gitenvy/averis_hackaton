#!/usr/bin/env python3
"""SDOC hackathon: ML email classifier (TF-IDF + logistic regression) + the
original SI/BL comparison stage (imported unchanged from hackathonprototype.py).

Usage
  # honest evaluation: out-of-fold predictions (each email is classified by a model
  # that never saw it), then the normal comparison stage
  python3 ml_pipeline.py --bundle BUNDLE --labels ground_truth.json --cv 5

  # train on all labelled data, save model, classify the inbox
  python3 ml_pipeline.py --bundle BUNDLE --labels ground_truth.json --train
  # later / on new mail (no labels needed):
  python3 ml_pipeline.py --bundle NEW_BUNDLE --model model.joblib
"""
from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path
from collections import Counter

import numpy as np
import joblib
from scipy.sparse import hstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import accuracy_score, f1_score, classification_report

sys.path.insert(0, str(Path(__file__).parent))
import hackathonprototype as hp   # original comparison stage + keyword fallback

CATEGORIES = ["BL_COMPARISON", "SI_REQUEST", "INVOICE_QUERY", "GENERAL", "SPAM"]
CONFIDENCE_THRESHOLD = 0.45


def structural_tokens(email: dict) -> str:
    """Vocabulary-independent evidence turned into pseudo-words."""
    atts = email.get("attachments", [])
    toks = [f"ATTCOUNT{min(len(atts), 3)}"]
    if any(re.search(r"_SI\.", a, re.I) for a in atts): toks.append("HASSIATT")
    if any(re.search(r"_BL\.", a, re.I) for a in atts): toks.append("HASBLATT")
    sender = email.get("from", "").lower()
    dom = sender.split("@")[-1]
    toks.append("DOMAIN_" + re.sub(r"[^a-z0-9]", "", dom))
    toks.append("TLD_" + re.sub(r"[^a-z0-9]", "", dom.rsplit(".", 1)[-1]))
    if re.match(r"(?i)^\s*re\b", email.get("subject", "")): toks.append("ISREPLY")
    return " ".join(toks)


class EmailClassifier:
    def __init__(self):
        self.subj_w = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=1)
        self.subj_c = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True)
        self.body_w = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=1)
        self.body_c = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True, max_features=30000)
        self.meta = TfidfVectorizer(token_pattern=r"\S+", lowercase=False)
        self.clf = LogisticRegression(C=20, max_iter=3000, class_weight="balanced")

    @staticmethod
    def _parts(emails):
        subj = [e.get("subject", "") for e in emails]
        body = [hp.remove_email_boilerplate(e.get("body", "")) for e in emails]
        meta = [structural_tokens(e) for e in emails]
        return subj, body, meta

    def _X(self, emails, fit=False):
        subj, body, meta = self._parts(emails)
        f = (lambda v, d: v.fit_transform(d)) if fit else (lambda v, d: v.transform(d))
        return hstack([f(self.subj_w, subj), f(self.subj_c, subj),
                       f(self.body_w, body), f(self.body_c, body), f(self.meta, meta)]).tocsr()

    def fit(self, emails, labels):
        self.clf.fit(self._X(emails, fit=True), labels)
        return self

    def predict_proba(self, emails):
        return self.clf.predict_proba(self._X(emails))

    def classify(self, email):
        """Return (category, confidence, reason). Structure > model > keyword fallback."""
        atts = email.get("attachments", [])
        si, bl = hp.find_si_bl_paths(atts)
        if si and bl:
            return "BL_COMPARISON", 1.0, "si_bl_attachment_pair"
        p = self.predict_proba([email])[0]
        i = int(np.argmax(p))
        if p[i] >= CONFIDENCE_THRESHOLD:
            return str(self.clf.classes_[i]), float(p[i]), "ml_model"
        kw = hp.classify_email(email)["category"]     # low confidence -> keyword scorer
        return kw, float(p[i]), "low_confidence_keyword_fallback"


def run_pipeline(inbox, emails, predictions):
    """predictions: {email_id: (category, conf, reason)} -> submission via the original stage 3."""
    submission, low_conf = {}, []
    for e in emails:
        cat, conf, reason = predictions[e["email_id"]]
        if cat == "BL_COMPARISON":
            decision, _ = hp.analyse_bl_comparison(inbox, e)
        else:
            decision = {"status": "OK", "review_reason": None, "has_defect": False, "defect_fields": []}
        submission[e["email_id"]] = {"category": cat, **decision}
        if reason != "ml_model" and reason != "si_bl_attachment_pair":
            low_conf.append(e["email_id"])
    return submission, low_conf


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", type=Path, required=True)
    ap.add_argument("--labels", type=Path, help="ground_truth.json (training / evaluation only)")
    ap.add_argument("--cv", type=int, help="k-fold out-of-fold evaluation")
    ap.add_argument("--train", action="store_true", help="fit on all labels and save model")
    ap.add_argument("--model", type=Path, default=Path("model.joblib"))
    ap.add_argument("--submission", type=Path, default=Path("ml_submission.json"))
    a = ap.parse_args()

    inbox = hp.load_inbox(a.bundle)
    emails = list(inbox)
    hp.ensure_attachment_dependencies(emails)
    ids = [e["email_id"] for e in emails]
    predictions = {}

    if a.cv:
        gt = json.loads(a.labels.read_text())
        y = np.array([gt[i]["category"] for i in ids])
        skf = StratifiedKFold(n_splits=a.cv, shuffle=True, random_state=0)
        for tr, te in skf.split(emails, y):
            m = EmailClassifier().fit([emails[i] for i in tr], y[tr])
            for i in te:
                predictions[ids[i]] = m.classify(emails[i])
        pred = np.array([predictions[i][0] for i in ids])
        print(f"[{a.cv}-fold out-of-fold] Stage-1 accuracy {accuracy_score(y, pred):.4f}  "
              f"macro-F1 {f1_score(y, pred, average='macro'):.4f}")
        print(classification_report(y, pred, digits=3))
        for i, t, p in zip(ids, y, pred):
            if t != p: print("  miss", i, t, "->", p, predictions[i][2], round(predictions[i][1], 2))
    else:
        if a.train:
            gt = json.loads(a.labels.read_text())
            m = EmailClassifier().fit(emails, [gt[i]["category"] for i in ids])
            joblib.dump(m, a.model); print("saved", a.model)
        else:
            m = joblib.load(a.model)
        for e in emails:
            predictions[e["email_id"]] = m.classify(e)

    submission, low = run_pipeline(inbox, emails, predictions)
    a.submission.write_text(json.dumps(submission, indent=2) + "\n")
    print("wrote", a.submission, "| low-confidence emails:", len(low))
    print("category totals:", dict(Counter(v["category"] for v in submission.values())))


if __name__ == "__main__":
    main()
