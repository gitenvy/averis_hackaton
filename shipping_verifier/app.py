"""AI Shipping Auditor - Streamlit dashboard.

Run:  streamlit run app.py

Reads submission.json (the hackathon format) and report.json (per-email decision source,
confidence and SI/BL field values), both written by main.py.
Tabs: Audit log | Document diff | Live tester | Accuracy vs ground truth | Supervisor portal
"""
import json
import os
import subprocess
import sys
from typing import Any, Dict, Optional

import pandas as pd
import streamlit as st

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

st.set_page_config(page_title="AI Shipping Auditor", page_icon="🚢", layout="wide", initial_sidebar_state="expanded")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MAIN_PY_PATH = os.path.join(BASE_DIR, "main.py")
SUBMISSION_JSON_PATH = os.path.join(BASE_DIR, "submission.json")
REPORT_JSON_PATH = os.path.join(BASE_DIR, "report.json")
for _p in (BASE_DIR, os.path.join(BASE_DIR, "data_averis", "server")):
    if _p not in sys.path:
        sys.path.append(_p)

TARGET_FIELDS = ["shipper", "consignee", "notify_party", "port_of_loading", "port_of_discharge",
                 "container_count", "gross_weight_kg"]
CATEGORIES = ["BL_COMPARISON", "SI_REQUEST", "INVOICE_QUERY", "GENERAL", "SPAM"]
SOURCE_LABELS = {
    "attachment_pair": "📎 Attachment rule",
    "ml_model": "🤖 Local ML model",
    "llm": "🧠 LLM (OpenRouter)",
    "keyword_fallback": "🔤 Keyword fallback",
    "n/a": "—",
}
RESULT_ICONS = {"MATCHED": "✅ Match", "NOT_MATCHED": "❌ Mismatch", "REVIEW_NEEDED": "⚠️ Needs review"}

EXAMPLES = {
    "— pick an example —": None,
    "Standard: request to compare": ("ops@seabridge-freight.com", "Please verify draft B/L - BK12345",
                                    "Hi, can you check the draft BL against the SI for booking BK12345? Thanks."),
    "Non-English (Chinese) comparison": ("ops@example.com", "核对提单", "你好，请核对附件中的提单草稿和装运指示，看看是否一致。谢谢。"),
    "Invoice question": ("acct@example.com", "Charges dispute", "We were billed USD 2,705 for BK12345 but expected less. Please send an itemised breakdown."),
    "Phishing (bank details change)": ("accounts@aprilasla.com", "Updated bank details for invoice 5250071354",
                                       "Due to an audit our bank details have changed. Please remit to the new account and confirm."),
    "Legit email with spam words": ("ops@example.com", "URGENT: claim for damaged cargo",
                                    "The consignee has filed a claim for water damage on container MSCU1234567. Please verify the survey report."),
    "Forwarded thread (top message decides)": ("ops@example.com", "RE: FW: vessel schedule",
                                               "Separate topic - we still need the shipping instruction for BK12345 by tomorrow noon.\n\n________________________________\nFrom: ops\nSubject: schedule\n\nThanks all, the vessel is on schedule."),
}


# ----------------------------------------------------------------------------- helpers
def get_secret(key_name: str, default: str = "") -> str:
    """Streamlit secrets -> environment (.env / system) -> default."""
    try:
        if hasattr(st, "secrets") and key_name in st.secrets:
            return str(st.secrets[key_name])
    except Exception:
        pass
    return os.getenv(key_name, default)


def _mtime(path: str) -> float:
    return os.path.getmtime(path) if os.path.exists(path) else 0.0


@st.cache_data
def load_json(path: str, mtime: float) -> Dict[str, Any]:  # mtime is part of the cache key
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def check_server_health(url: str) -> bool:
    if not HAS_REQUESTS or not url:
        return False
    try:
        return requests.get(f"{url.rstrip('/')}/health", timeout=2).status_code == 200
    except Exception:
        return False


def status_pill(status: str) -> str:
    cls = {"OK": ("badge-ok", "✅ Passed (OK)"), "MISMATCH": ("badge-mismatch", "❌ Discrepancy"),
           "NEEDS_REVIEW": ("badge-review", "⚠️ Needs Review")}.get(status)
    return f'<span class="{cls[0]}">{cls[1]}</span>' if cls else f"<span>{status}</span>"


def comparison_frame(comparisons: Optional[dict]) -> pd.DataFrame:
    rows = []
    for field in TARGET_FIELDS:
        c = (comparisons or {}).get(field, {})
        rows.append({
            "Field": field.replace("_", " ").title(),
            "SI value": c.get("si_raw") if c.get("si_raw") not in (None, "") else "—",
            "BL value": c.get("bl_raw") if c.get("bl_raw") not in (None, "") else "—",
            "SI label": c.get("si_label") or "—",
            "BL label": c.get("bl_label") or "—",
            "Result": RESULT_ICONS.get(c.get("result"), "—"),
        })
    return pd.DataFrame(rows)


def style_comparison(df: pd.DataFrame):
    def color(row):
        if "Mismatch" in row["Result"]:
            return ["background-color: rgba(248,81,73,0.18)"] * len(row)
        if "review" in row["Result"]:
            return ["background-color: rgba(210,153,34,0.18)"] * len(row)
        return [""] * len(row)
    return df.style.apply(color, axis=1)


class MemInbox:
    """Minimal in-memory stand-in for the loader's Inbox, used by the live tester."""
    def __init__(self, files: Dict[str, bytes]):
        self.files = files

    def read_bytes(self, path: str) -> bytes:
        return self.files[path]

    def read_text(self, path: str, encoding: str = "utf-8") -> str:
        return self.files[path].decode(encoding, errors="replace")


@st.cache_resource(show_spinner="Loading classifier...")
def load_engine():
    import classifier
    import hackathonprototype as hp
    return classifier, hp


def run_live(sender: str, subject: str, body: str, si_file, bl_file):
    classifier, hp = load_engine()
    files, attachments = {}, []
    for kind, up in (("SI", si_file), ("BL", bl_file)):
        if up is not None:
            ext = os.path.splitext(up.name)[1] or ".txt"
            path = f"attachments/live_{kind}{ext}"
            files[path] = up.getvalue()
            attachments.append(path)
    email = {"email_id": "live", "from": sender, "subject": subject, "body": body, "attachments": attachments}
    cls = classifier.classify_email_detailed(email)
    record = {"category": cls["category"], "status": "OK", "review_reason": None, "defect_fields": [], "has_defect": False}
    comparisons = None
    if cls["category"] == "BL_COMPARISON":
        decision, doc = hp.analyse_bl_comparison(MemInbox(files), email)
        record.update(decision)
        comparisons = ((doc or {}).get("comparison") or {}).get("comparisons")
    return cls, record, comparisons


def source_of(rec_detail: dict) -> str:
    return (rec_detail or {}).get("source", "n/a")


# ----------------------------------------------------------------------------- styling
st.markdown("""
<style>
    .stMetric { background: rgba(128,128,128,0.08); padding: 16px; border-radius: 10px; border: 1px solid rgba(128,128,128,0.25); }
    .badge-ok, .badge-mismatch, .badge-review { padding: 4px 12px; border-radius: 20px; font-weight: 600; font-size: 0.85rem; }
    .badge-ok { background-color: #0e4429; color: #3fb950; }
    .badge-mismatch { background-color: #4c1d1d; color: #f85149; }
    .badge-review { background-color: #4d2d00; color: #d29922; }
    .card { border: 1px solid rgba(128,128,128,0.3); border-radius: 10px; padding: 12px 16px; margin-bottom: 8px; }
    .muted { opacity: 0.7; font-size: 0.85rem; }
</style>
""", unsafe_allow_html=True)

if "hitl_decisions" not in st.session_state:
    st.session_state.hitl_decisions = {}

# ----------------------------------------------------------------------------- sidebar
with st.sidebar:
    st.title("🚢 Shipping Auditor")
    st.caption("AI Document Verification Engine v3.0 · hybrid ML + LLM")
    st.markdown("---")
    st.subheader("⚙️ Configuration")

    openrouter_key = st.text_input("OpenRouter API Key (optional)", value=get_secret("OPENROUTER_API_KEY", ""), type="password",
                                   help="Only used as a fallback when the local model is unsure. Leave empty to run fully free/offline.")
    eval_url = st.text_input("Evaluation Server URL", value=get_secret("EVAL_SERVER_URL", "http://localhost:8080"),
                             help="Leave empty to use a local dataset folder instead.")
    local_dir = st.text_input("Local dataset folder (optional)", value=get_secret("LOCAL_DATA_DIR", ""),
                              help="A folder containing inbox/ and attachments/, e.g. varied_dataset/unseen_test. Used when the server URL is empty or offline.")
    sample_size = st.slider("Sample size for batch run", 1, 520, 20, 5, help="How many emails to process.")

    if check_server_health(eval_url):
        st.success("🟢 Evaluation server connected")
    else:
        st.info("🟡 Offline / standalone dataset active")

    st.markdown("---")
    st.subheader("⚡ Quick Controls")
    if st.button("▶️ Run Audit Pipeline", type="primary", width="stretch"):
        if not os.path.exists(MAIN_PY_PATH):
            st.error(f"Cannot find `main.py` at `{MAIN_PY_PATH}`.")
        else:
            with st.status(f"Running audit pipeline on {sample_size} emails...", expanded=True) as status_box:
                env = os.environ.copy()
                env["EVAL_SERVER_URL"] = eval_url
                env["BATCH_LIMIT"] = str(sample_size)
                if local_dir:
                    env["LOCAL_DATA_DIR"] = local_dir
                if openrouter_key:
                    env["OPENROUTER_API_KEY"] = openrouter_key
                result = subprocess.run([sys.executable, MAIN_PY_PATH, "--limit", str(sample_size)],
                                        cwd=BASE_DIR, capture_output=True, text=True, env=env)
                if result.returncode == 0:
                    st.cache_data.clear()
                    status_box.update(label="Audit complete!", state="complete", expanded=False)
                    st.rerun()
                else:
                    status_box.update(label="Pipeline execution failed", state="error")
                    st.error(f"Error executing `main.py`:\n\n```text\n{result.stderr or result.stdout}\n```")

    st.markdown("---")
    _sub_raw = load_json(SUBMISSION_JSON_PATH, _mtime(SUBMISSION_JSON_PATH))
    if _sub_raw:
        st.download_button("📥 Download submission.json", json.dumps(_sub_raw, indent=2), "submission.json",
                           "application/json", width="stretch")

# ----------------------------------------------------------------------------- data
st.title("Automated Shipping Document Auditor")
st.markdown("Classify logistics emails, cross-check Shipping Instructions (SI) against draft Bills of Lading (BL), "
            "see **which stage made each decision and how confident it was**, and escalate the rest.")

data = load_json(SUBMISSION_JSON_PATH, _mtime(SUBMISSION_JSON_PATH))
report = load_json(REPORT_JSON_PATH, _mtime(REPORT_JSON_PATH))
if data:
    data = dict(list(data.items())[:sample_size])

rows = []
for eid, rec in data.items():
    det = report.get(eid, {})
    override = st.session_state.hitl_decisions.get(eid)
    conf = det.get("confidence")
    rows.append({
        "Email ID": eid,
        "Subject": det.get("subject", ""),
        "Category": rec.get("category", "GENERAL"),
        "Status": override["status"] if override else rec.get("status", "OK"),
        "Source": SOURCE_LABELS.get(source_of(det), source_of(det)),
        "_source": source_of(det),
        "Confidence": (conf * 100) if isinstance(conf, (int, float)) else None,
        "Review Reason": rec.get("review_reason") or "-",
        "Defect Fields": ", ".join(rec.get("defect_fields", [])) or "None",
        "Raw Defect List": rec.get("defect_fields", []),
        "Supervisor Notes": override["notes"] if override else "",
    })
df = pd.DataFrame(rows)

tab_log, tab_diff, tab_live, tab_acc, tab_hitl = st.tabs([
    "📊 Audit Summary & Logs", "🔍 Document Diff Inspector", "🧪 Live Tester",
    "🎯 Accuracy vs Ground Truth", "🚨 Supervisor Portal"])

# ============================================================ TAB 1: audit log
with tab_log:
    if df.empty:
        st.info("👋 **Welcome!** No results yet. Choose a sample size in the sidebar and click **▶️ Run Audit Pipeline**, "
                "or try the **🧪 Live Tester** tab to classify a single email right now.")
    else:
        total = len(df)
        ok_n, mm_n, rv_n = (int((df["Status"] == s).sum()) for s in ("OK", "MISMATCH", "NEEDS_REVIEW"))
        local_n = int(df["_source"].isin(["attachment_pair", "ml_model"]).sum())
        llm_n = int((df["_source"] == "llm").sum())
        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("Emails audited", total)
        k2.metric("Passed (OK)", ok_n, delta=f"{ok_n / total:.0%} auto-cleared")
        k3.metric("Discrepancies", mm_n, delta=f"{mm_n / total:.0%} mismatched", delta_color="inverse")
        k4.metric("Escalations", rv_n, delta=f"{rv_n / total:.0%} in queue", delta_color="off")
        k5.metric("Decided locally", f"{local_n / total:.0%}", delta=f"{llm_n} used the LLM", delta_color="off")
        st.markdown("---")

        f1, f2, f3, f4 = st.columns([2, 1, 1, 1])
        q = f1.text_input("🔍 Search (email ID, subject, category, field)", "")
        cat_f = f2.multiselect("Category", sorted(df["Category"].unique()), default=sorted(df["Category"].unique()))
        stat_f = f3.multiselect("Status", sorted(df["Status"].unique()), default=sorted(df["Status"].unique()))
        src_f = f4.multiselect("Decision source", sorted(df["Source"].unique()), default=sorted(df["Source"].unique()))
        view = df[df["Category"].isin(cat_f) & df["Status"].isin(stat_f) & df["Source"].isin(src_f)]
        only_unsure = st.checkbox("Show only low-confidence / fallback decisions (best candidates for LLM or human review)")
        if only_unsure:
            view = view[(view["_source"].isin(["keyword_fallback", "llm"])) | (view["Confidence"].fillna(100) < 60)]
        if q:
            ql = q.lower()
            view = view[view["Email ID"].str.lower().str.contains(ql) | view["Subject"].str.lower().str.contains(ql)
                        | view["Category"].str.lower().str.contains(ql) | view["Defect Fields"].str.lower().str.contains(ql)]

        st.markdown(f"Showing **{len(view)}** of **{total}** records")
        st.dataframe(
            view[["Email ID", "Subject", "Category", "Status", "Source", "Confidence", "Review Reason", "Defect Fields", "Supervisor Notes"]],
            width="stretch", hide_index=True,
            column_config={
                "Confidence": st.column_config.ProgressColumn("Confidence", min_value=0, max_value=100, format="%.0f%%"),
                "Status": st.column_config.TextColumn("Audit result"),
                "Defect Fields": st.column_config.TextColumn("Flagged discrepancies", width="large"),
            })

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("##### Category distribution")
            st.bar_chart(df["Category"].value_counts())
        with c2:
            st.markdown("##### Who made the decision?")
            st.bar_chart(df["Source"].value_counts())
        if not report:
            st.caption("report.json not found - re-run the pipeline to see decision sources and confidence.")

# ============================================================ TAB 2: diff inspector
with tab_diff:
    st.subheader("Field-level SI vs BL comparison")
    if df.empty:
        st.info("Run the pipeline first.")
    else:
        scope = st.radio("Show:", ["Mismatches & escalations only", "All BL comparisons", "All records"], horizontal=True)
        if scope.startswith("Mismatches"):
            ids = df[df["Status"].isin(["MISMATCH", "NEEDS_REVIEW"])]["Email ID"].tolist()
        elif scope.startswith("All BL"):
            ids = df[df["Category"] == "BL_COMPARISON"]["Email ID"].tolist()
        else:
            ids = df["Email ID"].tolist()
        if not ids:
            st.success("No records to inspect for this filter.")
        else:
            sel = st.selectbox("Select an email", ids)
            row = df[df["Email ID"] == sel].iloc[0]
            det = report.get(sel, {})
            h1, h2, h3 = st.columns(3)
            h1.markdown(f"**Email:** `{sel}`")
            h2.markdown(f"**Category:** `{row['Category']}`")
            h3.markdown(f"**Status:** {status_pill(row['Status'])}", unsafe_allow_html=True)

            left, right = st.columns([3, 2])
            with left:
                st.markdown(f"**Subject:** {det.get('subject', '—')}")
                st.markdown(f"**From:** `{det.get('from', '—')}`")
                with st.expander("Email body", expanded=False):
                    st.text(det.get("body_preview", "(not stored - re-run the pipeline)"))
                if det.get("attachments"):
                    st.markdown("**Attachments:** " + ", ".join(f"`{os.path.basename(a)}`" for a in det["attachments"]))
            with right:
                st.markdown(f"**Decision source:** {SOURCE_LABELS.get(source_of(det), source_of(det))}")
                if det.get("confidence") is not None:
                    st.progress(min(max(float(det["confidence"]), 0.0), 1.0), text=f"Confidence {det['confidence']:.0%}")
                if det.get("probabilities"):
                    st.bar_chart(pd.Series(det["probabilities"]).sort_values(ascending=False))
                if det.get("note"):
                    st.caption(det["note"])

            st.markdown("---")
            if row["Category"] != "BL_COMPARISON":
                st.info("This email was not routed to SI-vs-BL comparison, so there are no field values to compare.")
            elif det.get("comparisons"):
                cdf = comparison_frame(det["comparisons"])
                st.dataframe(style_comparison(cdf), width="stretch", hide_index=True)
                bad = [f for f in row["Raw Defect List"]]
                if bad:
                    st.error("Flagged discrepancies: " + ", ".join(f"`{b}`" for b in bad))
            else:
                reason = row["Review Reason"]
                st.warning(f"No field values could be compared (`{reason}`).")
                for k, v in (det.get("errors") or {}).items():
                    st.code(f"{k}: {v}")

# ============================================================ TAB 3: live tester
with tab_live:
    st.subheader("Test a single email")
    st.caption("Paste an email (and optionally the SI and draft BL files). Nothing is saved - this runs the same classifier and comparison engine as the batch pipeline.")
    ex = st.selectbox("Load an example", list(EXAMPLES))
    ex_vals = EXAMPLES[ex] or ("", "", "")
    with st.form("live_form"):
        c1, c2 = st.columns(2)
        sender = c1.text_input("From", value=ex_vals[0], key=f"from_{ex}")
        subject = c2.text_input("Subject", value=ex_vals[1], key=f"subj_{ex}")
        body = st.text_area("Body", value=ex_vals[2], height=160, key=f"body_{ex}")
        u1, u2 = st.columns(2)
        si_up = u1.file_uploader("Shipping Instruction (SI)", type=["txt", "pdf", "docx", "xlsx"], key="live_si")
        bl_up = u2.file_uploader("Draft Bill of Lading (BL)", type=["txt", "pdf", "docx", "xlsx"], key="live_bl")
        go = st.form_submit_button("Classify & compare", type="primary")
    if go:
        if not (subject or body or si_up or bl_up):
            st.warning("Enter a subject/body or upload a file first.")
        else:
            try:
                cls, rec, comps = run_live(sender, subject, body, si_up, bl_up)
            except Exception as exc:
                st.error(f"Engine error: {exc}")
                st.stop()
            r1, r2, r3, r4 = st.columns(4)
            r1.metric("Category", cls["category"])
            r2.metric("Status", rec["status"])
            r3.metric("Decided by", SOURCE_LABELS.get(cls["source"], cls["source"]))
            r4.metric("Confidence", f"{cls['confidence']:.0%}" if cls["confidence"] is not None else "—")
            if cls.get("probabilities"):
                st.markdown("##### Model probabilities")
                st.bar_chart(pd.Series(cls["probabilities"]).sort_values(ascending=False))
            if cls.get("note"):
                st.info(cls["note"])
            if cls["category"] == "BL_COMPARISON":
                st.markdown("##### SI vs BL")
                if comps:
                    st.dataframe(style_comparison(comparison_frame(comps)), width="stretch", hide_index=True)
                    if rec["defect_fields"]:
                        st.error("Discrepancies: " + ", ".join(f"`{f}`" for f in rec["defect_fields"]))
                    elif rec["status"] == "OK":
                        st.success("All 7 fields match.")
                if rec["status"] == "NEEDS_REVIEW":
                    st.warning(f"Needs review: `{rec['review_reason']}`")
            with st.expander("Raw decision record"):
                st.json(rec)

# ============================================================ TAB 4: accuracy
with tab_acc:
    st.subheader("Score the current results against a ground truth")
    st.caption("Upload the `ground_truth.json` for the dataset you ran (from the docker bundle or a `varied_dataset` split). "
               "Only emails present in the current results are scored.")
    gt_up = st.file_uploader("ground_truth.json", type=["json"], key="gt_upload")
    truth = None
    if gt_up is not None:
        try:
            truth = json.load(gt_up)
        except Exception as exc:
            st.error(f"Could not read that file: {exc}")
    if df.empty:
        st.info("Run the pipeline first.")
    elif truth is None:
        st.info("Upload a ground truth file to see accuracy.")
    else:
        sub_full = load_json(SUBMISSION_JSON_PATH, _mtime(SUBMISSION_JSON_PATH))
        ids = [e for e in data if e in truth]
        if not ids:
            st.error("None of the processed email IDs appear in this ground truth. Did you run the same dataset?")
        else:
            t = {e: truth[e] for e in ids}
            s = {e: sub_full[e] for e in ids}
            try:
                import scoring
                res = scoring.score_all(t, s)
                st.metric("FINAL SCORE (tester formula)", f"{res['final_score']:.4f}")
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Stage 1 accuracy", f"{res['stage1']['accuracy']:.1%}")
                m2.metric("Stage 1 macro-F1", f"{res['stage1']['macro_f1']:.3f}")
                m3.metric("Defect F1 (stage 3)", f"{res['stage3']['defect_f1']:.3f}")
                m4.metric("End-to-end defects caught", f"{res['end_to_end']['success']}/{res['end_to_end']['total']}")
                per = []
                for c in CATEGORIES:
                    d = res["stage1"]["per"][c]
                    p = d["tp"] / (d["tp"] + d["fp"]) if d["tp"] + d["fp"] else 0.0
                    r = d["tp"] / (d["tp"] + d["fn"]) if d["tp"] + d["fn"] else 0.0
                    per.append({"Category": c, "Precision": round(p, 3), "Recall": round(r, 3),
                                "F1": round(2 * p * r / (p + r), 3) if p + r else 0.0, "Emails": d["tp"] + d["fn"]})
                st.markdown("##### Per-category performance")
                st.dataframe(pd.DataFrame(per), hide_index=True, width="stretch")
                conf = pd.DataFrame(res["stage1"]["confusion"]).T.reindex(index=CATEGORIES, columns=CATEGORIES).fillna(0).astype(int)
                conf.index.name = "Actual ↓ / Predicted →"
                st.markdown("##### Confusion matrix")
                st.dataframe(conf, width="stretch")
                rel = res["reliability"]
                st.caption(f"NEEDS_REVIEW escalation: recall {rel['escalation_recall']:.2f}, precision {rel['escalation_precision']:.2f}")
            except Exception as exc:
                st.warning(f"Official scoring module unavailable ({exc}); showing accuracy only.")
                acc = sum(t[e]["category"] == s[e]["category"] for e in ids) / len(ids)
                st.metric("Category accuracy", f"{acc:.1%}")

            # accuracy by decision source, and the misses
            table = []
            for e in ids:
                det = report.get(e, {})
                table.append({"Email ID": e, "Subject": det.get("subject", ""), "Actual": t[e]["category"],
                              "Predicted": s[e]["category"], "Correct": t[e]["category"] == s[e]["category"],
                              "Source": SOURCE_LABELS.get(source_of(det), source_of(det)),
                              "Confidence": (det.get("confidence") or 0) * 100 if det.get("confidence") is not None else None})
            tdf = pd.DataFrame(table)
            st.markdown("##### Accuracy by decision source")
            by_src = tdf.groupby("Source")["Correct"].agg(["mean", "count"]).rename(columns={"mean": "Accuracy", "count": "Emails"})
            by_src["Accuracy"] = (by_src["Accuracy"] * 100).round(1)
            st.dataframe(by_src, width="stretch")
            st.caption("If the local model is much less accurate than the LLM on low-confidence emails, raise the confidence threshold in ml_pipeline.py.")
            wrong = tdf[~tdf["Correct"]]
            st.markdown(f"##### Misclassified emails ({len(wrong)})")
            if wrong.empty:
                st.success("No category errors in this sample.")
            else:
                st.dataframe(wrong.drop(columns=["Correct"]), hide_index=True, width="stretch",
                             column_config={"Confidence": st.column_config.ProgressColumn("Confidence", min_value=0, max_value=100, format="%.0f%%")})

# ============================================================ TAB 5: supervisor portal
with tab_hitl:
    st.subheader("Supervisor decision portal")
    st.caption("Review flagged items, apply manual overrides, and log notes. Overrides live in this browser session only.")
    if df.empty:
        st.info("Run the pipeline first.")
    else:
        queue = df[df["Status"].isin(["NEEDS_REVIEW", "MISMATCH"])]
        if st.checkbox("Also include low-confidence classifications (< 60%)"):
            queue = df[df["Status"].isin(["NEEDS_REVIEW", "MISMATCH"]) | (df["Confidence"].fillna(100) < 60)]
        if queue.empty:
            st.success("🎉 Nothing in the escalation queue.")
        else:
            qc1, qc2 = st.columns(2)
            with qc1:
                st.markdown("#### Pending queue")
                st.dataframe(queue[["Email ID", "Category", "Status", "Confidence", "Review Reason", "Defect Fields"]],
                             width="stretch", hide_index=True,
                             column_config={"Confidence": st.column_config.ProgressColumn("Confidence", min_value=0, max_value=100, format="%.0f%%")})
            with qc2:
                st.markdown("#### Action console")
                target = st.selectbox("Record to resolve", queue["Email ID"].tolist())
                cur = queue[queue["Email ID"] == target].iloc[0]
                st.info(f"**Reason:** `{cur['Review Reason']}` | **Defects:** `{cur['Defect Fields']}` | **Source:** {cur['Source']}")
                notes = st.text_area("Audit notes / justification", placeholder="e.g. Verified with carrier by phone; discrepancy approved.")
                a1, a2 = st.columns(2)
                if a1.button("✅ Force approve (mark OK)", width="stretch", type="primary"):
                    st.session_state.hitl_decisions[target] = {"status": "OK", "notes": notes or "Manually approved by supervisor"}
                    st.rerun()
                if a2.button("🚨 Escalate to freight forwarder", width="stretch"):
                    st.session_state.hitl_decisions[target] = {"status": "NEEDS_REVIEW", "notes": notes or "Escalated externally to forwarder"}
                    st.rerun()
        if st.session_state.hitl_decisions:
            with st.expander(f"Decisions made this session ({len(st.session_state.hitl_decisions)})"):
                st.json(st.session_state.hitl_decisions)
