import os
import json
import requests
import pandas as pd
import streamlit as st
from typing import Dict, Any

# Page Setup
st.set_page_config(
    page_title="SDOC | AI Shipping Auditor",
    page_icon="🚢",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Styling for Badges & Clean Layout
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


# Initialize Session State for HITL Decisions
if "hitl_decisions" not in st.session_state:
    st.session_state.hitl_decisions = {}


@st.cache_data
def load_submission_data(file_path: str = "submission.json") -> Dict[str, Any]:
    """Loads and caches submission JSON results."""
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def check_server_health(url: str) -> bool:
    """Checks if the FastAPI/Docker evaluation server is reachable."""
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


# --- SIDEBAR CONTROL PANEL ---
with st.sidebar:
    st.title("🚢 SDOC Auditor")
    st.caption("AI Shipping Verification Engine v2.0")
    st.markdown("---")

    # Server Status Indicator
    eval_url = st.text_input(
        "Evaluation Server URL",
        value=os.getenv("EVAL_SERVER_URL", "http://localhost:8080"),
        help="FastAPI / Docker endpoint"
    )
    
    server_online = check_server_health(eval_url)
    if server_online:
        st.success("🟢 Evaluation Server Connected")
    else:
        st.warning("🔴 Server Unreachable (Check Docker)")

    st.markdown("---")
    st.subheader("⚡ Quick Controls")

    if st.button("▶️ Run Audit Pipeline", type="primary", use_container_width=True):
        with st.status("Executing 520-email audit pipeline...", expanded=True) as status_box:
            st.write("Fetching inbox records...")
            st.write("Classifying intent & extracting entities...")
            exit_code = os.system("python main.py")
            if exit_code == 0:
                st.cache_data.clear()
                status_box.update(label="Audit Complete!", state="complete", expanded=False)
                st.success("Results updated successfully!")
                st.rerun()
            else:
                status_box.update(label="Pipeline Execution Failed", state="error")
                st.error("Error executing `main.py`. Check terminal logs.")

    st.markdown("---")
    # Export Data
    data_raw = load_submission_data()
    if data_raw:
        json_str = json.dumps(data_raw, indent=2)
        st.download_button(
            label="📥 Download submission.json",
            data=json_str,
            file_name="submission.json",
            mime="application/json",
            use_container_width=True
        )


# --- MAIN HEADER ---
st.title("Automated Shipping Document Auditor")
st.markdown("Parse logistics communications, cross-examine Shipping Instructions (SI) against Bills of Lading (BL), and escalate edge cases automatically.")

# Load Submission Data
data = load_submission_data()

if not data:
    st.info("👋 **Welcome!** No evaluation output found yet (`submission.json`). Click **▶️ Run Audit Pipeline** in the sidebar to process the inbox dataset.")
    st.stop()

# Build DataFrame with HITL Overrides Applied
rows = []
for eid, rec in data.items():
    # Apply supervisor session state overrides if present
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

# --- KPI METRIC CARDS ---
k1, k2, k3, k4 = st.columns(4)
k1.metric("Total Emails Audited", total_emails)
k2.metric("Passed (OK)", f"{ok_count}", delta=f"{ok_count/total_emails*100:.1f}% Auto-cleared")
k3.metric("Discrepancies", f"{mismatch_count}", delta=f"{mismatch_count/total_emails*100:.1f}% Mismatched", delta_color="inverse")
k4.metric("Escalations", f"{review_count}", delta=f"{review_count/total_emails*100:.1f}% In Queue", delta_color="off")

st.markdown("---")

# --- WORKSPACE TABS ---
tab1, tab2, tab3 = st.tabs([
    "📊 Audit Summary & Logs", 
    "🔍 Document Diff Inspector", 
    "🚨 Supervisor Escalation Portal"
])


# ==========================================
# TAB 1: AUDIT SUMMARY & LOGS
# ==========================================
with tab1:
    st.subheader("Interactive Audit Log")

    # Filter Controls Bar
    f_col1, f_col2, f_col3 = st.columns([2, 1, 1])
    with f_col1:
        search_query = st.text_input("🔍 Quick Search (Email ID, Field Name, Category)", "")
    with f_col2:
        category_filter = st.multiselect("Category", options=df["Category"].unique(), default=df["Category"].unique())
    with f_col3:
        status_filter = st.multiselect("Status", options=df["Status"].unique(), default=df["Status"].unique())

    # Apply Filters
    filtered_df = df[
        (df["Category"].isin(category_filter)) & 
        (df["Status"].isin(status_filter))
    ]

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
        use_container_width=True,
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


# ==========================================
# TAB 2: DOCUMENT DIFF INSPECTOR
# ==========================================
with tab2:
    st.subheader("Field-Level Discrepancy Matrix")

    # Filter selector to target interesting items quickly
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
            
            # Header info
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

            # Dynamic Diff Table
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


# ==========================================
# TAB 3: HUMAN-IN-THE-LOOP (HITL) PORTAL
# ==========================================
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
                use_container_width=True,
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
                if st.button("✅ Force Approve (Mark OK)", use_container_width=True, type="primary"):
                    st.session_state.hitl_decisions[target_id] = {
                        "status": "OK",
                        "notes": supervisor_notes or "Manually approved by supervisor"
                    }
                    st.success(f"Record `{target_id}` updated to OK!")
                    st.rerun()

            with act_c2:
                if st.button("🚨 Escalate to Freight Forwarder", use_container_width=True):
                    st.session_state.hitl_decisions[target_id] = {
                        "status": "NEEDS_REVIEW",
                        "notes": supervisor_notes or "Escalated externally to forwarder"
                    }
                    st.warning(f"Escalation ticket generated for `{target_id}`.")
                    st.rerun()