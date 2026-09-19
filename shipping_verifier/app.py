import os
import sys
import json
import subprocess
import pandas as pd
import streamlit as st
from typing import Dict, Any

# Safe requests import
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

# 1. Page Configuration (MUST be the first Streamlit command)
st.set_page_config(
    page_title="SDOC | AI Shipping Auditor",
    page_icon="🚢",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 2. Path Resolution
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MAIN_PY_PATH = os.path.join(BASE_DIR, "main.py")
SUBMISSION_JSON_PATH = os.path.join(BASE_DIR, "submission.json")

# 3. CSS Styling
st.markdown("""
<style>
    .stMetric {
        background: #161b22;
        padding: 16px;
        border-radius: 10px;
        border: 1px solid #30363d;
    }
    .badge-ok {
        background-color: #0e4429;
        color: #3fb950;
        padding: 4px 12px;
        border-radius: 20px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .badge-mismatch {
        background-color: #4c1d1d;
        color: #f85149;
        padding: 4px 12px;
        border-radius: 20px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .badge-review {
        background-color: #4d2d00;
        color: #d29922;
        padding: 4px 12px;
        border-radius: 20px;
        font-weight: 600;
        font-size: 0.85rem;
    }
</style>
""", unsafe_allow_html=True)

if "hitl_decisions" not in st.session_state:
    st.session_state.hitl_decisions = {}


@st.cache_data
def load_submission_data(file_path: str = SUBMISSION_JSON_PATH) -> Dict[str, Any]:
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def check_server_health(url: str) -> bool:
    if not HAS_REQUESTS:
        return False
    try:
        res = requests.get(f"{url.rstrip('/')}/health", timeout=2)
        return res.status_code == 200
    except Exception:
        return False


def render_status_pill(status: str) -> str:
    if status == "OK":
        return '<span class="badge-ok">✅ Passed (OK)</span>'
    elif status == "MISMATCH":
        return '<span class="badge-mismatch">❌ Discrepancy</span>'
    elif status == "NEEDS_REVIEW":
        return '<span class="badge-review">⚠️ Needs Review</span>'
    return f'<span>{status}</span>'


# SIDEBAR
with st.sidebar:
    st.title("🚢 SDOC Auditor")
    st.caption("AI Shipping Verification Engine v2.0")
    st.markdown("---")

    st.subheader("⚙️ Configuration")
    
    eval_url = st.text_input(
        "Evaluation Server URL",
        value=os.getenv("EVAL_SERVER_URL", "http://localhost:8080"),
        help="FastAPI / Docker endpoint or Tunnel URL"
    )

    sample_size = st.slider(
        "Sample size for batch run",
        min_value=1,
        max_value=520,
        value=20,
        step=5,
        help="Control how many emails from the inbox dataset to process."
    )

    server_online = check_server_health(eval_url)
    if server_online:
        st.success("🟢 Evaluation Server Connected")
    else:
        st.warning("🔴 Server Unreachable (Check Tunnel/Docker)")

    st.markdown("---")
    st.subheader("⚡ Quick Controls")

    if st.button("▶️ Run Audit Pipeline", type="primary", width="stretch"):
        if not os.path.exists(MAIN_PY_PATH):
            st.error(f"Cannot find `main.py` at expected path: `{MAIN_PY_PATH}`.")
        else:
            with st.status(f"Executing audit pipeline on {sample_size} emails...", expanded=True) as status_box:
                st.write("Initializing inbox connection...")
                st.write(f"Classifying intent & extracting entities (limit = {sample_size})...")
                
                env = os.environ.copy()
                env["EVAL_SERVER_URL"] = eval_url
                env["BATCH_LIMIT"] = str(sample_size)
                
                result = subprocess.run(
                    [sys.executable, MAIN_PY_PATH, "--limit", str(sample_size)],
                    cwd=BASE_DIR,
                    capture_output=True,
                    text=True,
                    env=env
                )
                
                if result.returncode == 0:
                    st.cache_data.clear()
                    status_box.update(label="Audit Complete!", state="complete", expanded=False)
                    st.success(f"Successfully processed {sample_size} emails!")
                    st.rerun()
                else:
                    status_box.update(label="Pipeline Execution Failed", state="error")
                    st.error(f"Error executing `main.py`:\n\n```text\n{result.stderr or result.stdout}\n```")

    st.markdown("---")
    data_raw = load_submission_data()
    if data_raw:
        st.download_button(
            label="📥 Download submission.json",
            data=json.dumps(data_raw, indent=2),
            file_name="submission.json",
            mime="application/json",
            width="stretch"
        )


# MAIN DASHBOARD
st.title("Automated Shipping Document Auditor")
st.markdown("Parse logistics communications, cross-examine Shipping Instructions (SI) against Bills of Lading (BL), and escalate edge cases automatically.")

data = load_submission_data()

# Strictly cap data to sample_size
if data:
    data = dict(list(data.items())[:sample_size])

if not data:
    st.info("👋 **Welcome!** No evaluation output found yet (`submission.json`). Select a sample size in the sidebar and click **▶️ Run Audit Pipeline** to process the inbox dataset.")
    st.stop()

# Build DataFrame
rows = []
for eid, rec in data.items():
    override = st.session_state.hitl_decisions.get(eid)
    status = override["status"] if override else rec.get("status", "OK")
    notes = override["notes"] if override else ""
    
    rows.append({
        "Email ID": eid,
        "Category": rec.get("category", "GENERAL"),
        "Status": status,
        "Review Reason": rec.get("review_reason") or "-",
        "Defect Fields": ", ".join(rec.get("defect_fields", [])) if rec.get("defect_fields") else "None",
        "Has Defect": rec.get("has_defect", False),
        "Raw Defect List": rec.get("defect_fields", []),
        "Supervisor Notes": notes
    })

df = pd.DataFrame(rows)
total_emails = len(df)
ok_count = len(df[df["Status"] == "OK"])
mismatch_count = len(df[df["Status"] == "MISMATCH"])
review_count = len(df[df["Status"] == "NEEDS_REVIEW"])

# KPI METRIC CARDS
k1, k2, k3, k4 = st.columns(4)
k1.metric("Total Emails Audited", total_emails)
k2.metric("Passed (OK)", f"{ok_count}", delta=f"{ok_count/total_emails*100:.1f}% Auto-cleared" if total_emails else "0%")
k3.metric("Discrepancies", f"{mismatch_count}", delta=f"{mismatch_count/total_emails*100:.1f}% Mismatched" if total_emails else "0%", delta_color="inverse")
k4.metric("Escalations", f"{review_count}", delta=f"{review_count/total_emails*100:.1f}% In Queue" if total_emails else "0%", delta_color="off")

st.markdown("---")

tab1, tab2, tab3 = st.tabs([
    "📊 Audit Summary & Logs", 
    "🔍 Document Diff Inspector", 
    "🚨 Supervisor Escalation Portal"
])

# TAB 1: AUDIT SUMMARY & LOGS
with tab1:
    st.subheader("Interactive Audit Log")

    f_col1, f_col2, f_col3 = st.columns([2, 1, 1])
    with f_col1:
        search_query = st.text_input("🔍 Quick Search (Email ID, Field Name, Category)", "")
    with f_col2:
        category_filter = st.multiselect("Category", options=df["Category"].unique(), default=df["Category"].unique())
    with f_col3:
        status_filter = st.multiselect("Status", options=df["Status"].unique(), default=df["Status"].unique())

    filtered_df = df[(df["Category"].isin(category_filter)) & (df["Status"].isin(status_filter))]

    if search_query:
        sq = search_query.lower()
        filtered_df = filtered_df[
            filtered_df["Email ID"].str.lower().str.contains(sq) |
            filtered_df["Category"].str.lower().str.contains(sq) |
            filtered_df["Defect Fields"].str.lower().str.contains(sq)
        ]

    st.markdown(f"Displaying **{len(filtered_df)}** of **{total_emails}** records")

    st.dataframe(
        filtered_df[["Email ID", "Category", "Status", "Review Reason", "Defect Fields", "Supervisor Notes"]],
        width="stretch",
        hide_index=True,
        column_config={
            "Email ID": st.column_config.TextColumn("Email ID", width="small"),
            "Category": st.column_config.TextColumn("Category", width="medium"),
            "Status": st.column_config.TextColumn("Audit Result", width="medium"),
            "Review Reason": st.column_config.TextColumn("Reason for Review", width="medium"),
            "Defect Fields": st.column_config.TextColumn("Flagged Discrepancies", width="large"),
            "Supervisor Notes": st.column_config.TextColumn("HITL Notes", width="medium"),
        }
    )

    st.markdown("### Category Distribution")
    cat_counts = df["Category"].value_counts().reset_index()
    cat_counts.columns = ["Category", "Count"]
    st.bar_chart(cat_counts.set_index("Category"))

# TAB 2: DOCUMENT DIFF INSPECTOR
with tab2:
    st.subheader("Field-Level Discrepancy Matrix")

    inspect_type = st.radio("Show Email Records:", ["Mismatches & Escalations Only", "All Records"], horizontal=True)
    
    if inspect_type == "Mismatches & Escalations Only":
        selectable_ids = df[df["Status"].isin(["MISMATCH", "NEEDS_REVIEW"])]["Email ID"].tolist()
    else:
        selectable_ids = df["Email ID"].tolist()

    if not selectable_ids:
        st.success("No discrepancy records found for inspection!")
    else:
        selected_id = st.selectbox("Select Email Record to Cross-Examine", options=selectable_ids)

        if selected_id:
            record_row = df[df["Email ID"] == selected_id].iloc[0]
            
            ic1, ic2, ic3 = st.columns(3)
            ic1.markdown(f"**Selected Email:** `{selected_id}`")
            ic2.markdown(f"**Intent Category:** `{record_row['Category']}`")
            ic3.markdown(f"**Current Status:** {render_status_pill(record_row['Status'])}", unsafe_allow_html=True)

            st.markdown("---")

            target_fields = [
                "shipper", "consignee", "notify_party", 
                "port_of_loading", "port_of_discharge", 
                "container_count", "gross_weight_kg"
            ]

            defect_list = record_row["Raw Defect List"]

            diff_data = []
            for field in target_fields:
                is_mismatch = field in defect_list
                diff_data.append({
                    "Canonical Field": field.replace("_", " ").title(),
                    "Field Key": f"`{field}`",
                    "Audit Result": "❌ Mismatch Detected" if is_mismatch else "✅ Match",
                    "Action Needed": "Requires Operator Check" if is_mismatch else "Verified"
                })

            st.table(pd.DataFrame(diff_data))

# TAB 3: HUMAN-IN-THE-LOOP PORTAL
with tab3:
    st.subheader("Supervisor Decision Portal")
    st.caption("Review flagged escalations, apply manual audit overrides, and log notes.")

    review_queue = df[df["Status"].isin(["NEEDS_REVIEW", "MISMATCH"])]

    if review_queue.empty:
        st.balloons()
        st.success("🎉 All documents have passed automated audit cleanly! Zero items in human escalation queue.")
    else:
        q_col1, q_col2 = st.columns([1, 1])

        with q_col1:
            st.markdown("#### Pending Escalation Queue")
            st.dataframe(
                review_queue[["Email ID", "Status", "Review Reason", "Defect Fields"]],
                width="stretch",
                hide_index=True
            )

        with q_col2:
            st.markdown("#### Action Console")
            target_id = st.selectbox("Select Record to Resolve", options=review_queue["Email ID"].tolist())
            
            curr_rec = review_queue[review_queue["Email ID"] == target_id].iloc[0]
            st.info(f"**Reason Flagged:** `{curr_rec['Review Reason']}` | **Defects:** `{curr_rec['Defect Fields']}`")

            supervisor_notes = st.text_area("Audit Notes / Resolution Justification", placeholder="e.g. Verified with carrier via phone. Discrepancy approved.")

            act_c1, act_c2 = st.columns(2)
            
            with act_c1:
                if st.button("✅ Force Approve (Mark OK)", width="stretch", type="primary"):
                    st.session_state.hitl_decisions[target_id] = {
                        "status": "OK",
                        "notes": supervisor_notes or "Manually approved by supervisor"
                    }
                    st.success(f"Record `{target_id}` updated to OK!")
                    st.rerun()

            with act_c2:
                if st.button("🚨 Escalate to Freight Forwarder", width="stretch"):
                    st.session_state.hitl_decisions[target_id] = {
                        "status": "NEEDS_REVIEW",
                        "notes": supervisor_notes or "Escalated externally to forwarder"
                    }
                    st.warning(f"Escalation ticket generated for `{target_id}`.")
                    st.rerun()