"""Train the local email classifier once and save model.joblib.

  python train_model.py --bundle path/to/bundle_with_inbox_dir --labels ground_truth.json
"""
import argparse, json
from pathlib import Path
import joblib
import ml_pipeline as ml          # import as a module so the pickle can be loaded by main.py
import hackathonprototype as hp

ap = argparse.ArgumentParser()
ap.add_argument("--bundle", type=Path, required=True)
ap.add_argument("--labels", type=Path, required=True)
ap.add_argument("--out", type=Path, default=Path(__file__).with_name("model.joblib"))
a = ap.parse_args()
emails = list(hp.load_inbox(a.bundle))
gt = json.loads(a.labels.read_text())
model = ml.EmailClassifier().fit(emails, [gt[e["email_id"]]["category"] for e in emails])
joblib.dump(model, a.out)
print(f"trained on {len(emails)} emails -> {a.out}")
