import os
import json
import pandas as pd
import streamlit as st
from typing import Dict, Any

# Page Configuration
st.set_page_config(
    page_title="SDOC | Shipping Document Auditor",
    page_icon="🚢",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Badge Styling
st.markdown("""
<style>
    .stMetric {
        background-color: #0e1117;
        padding: 15px;
        border-radius: 8px;
        border: 1px solid #262730;
    }
    .badge-ok {
        background-color: #1e4620;
        color: #85e89d;
        padding: 4px 10px;
        border-radius: 4px;
        font-weight: bold;
    }
    .badge-mismatch {
        background-color: #4c1d1d;
        color: #f97583;
        padding: 4px 10px;
        border-radius: 4px;
        font-weight: bold;
    }
    .badge-review {
        background-color: #4a3319;
        color: #ffab70;
        padding: 4px 10px;
        border-radius: 4px;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)


@st.cache_data
def load_submission_data(file_path: str = "submission.json") -> Dict[str, Any]:
    """Loads and caches submission JSON data."""
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def render_status_badge(status: str) -> str:
    """Returns styled HTML badge for status values."""
    if status == "OK":
        return '<span class="badge-ok">✅ OK</span>'
    elif status == "MISMATCH":
        return '<span class="badge-mismatch">❌ MISMATCH</span>'
    elif status == "NEEDS_REVIEW":
        return '<span class="badge-review">⚠️ NEEDS REVIEW</span>'
    return f'<span>{status}</span>'


# --- SIDEBAR CONFIGURATION ---
with st.sidebar:
    st.image("https://img.icons8.com/color/96/cargo-ship.png", width=64)
    st.title("SDOC Control Panel")
    st.caption("Automated Shipping Document Auditor v2.0")

    st.markdown("---")
    st.subheader("⚙️ System Configuration")

    openrouter_key = st.text_input(
        "OpenRouter API Key",
        value=os.getenv("OPENROUTER_API_KEY", ""),
        type="password",
        help="API key for cloud inference execution."
    )

    model_choice = st.selectbox(
        "Active LLM Model",
        options=[
            "meta-llama/llama-3.3-70b-instruct",
            "anthropic/claude-3.5-sonnet",
            "deepseek/deepseek-chat",
            "qwen/qwen-2.5-72b-instruct"
        ],
        index=0
    )

    eval_url = st.text_input(
        "Evaluation Server URL",
        value=os.getenv("EVAL_SERVER_URL", "http://localhost:8080"),
        help="Containerized evaluation server endpoint."
    )

    st.markdown("---")
    if st.button("🚀 Execute Audit Pipeline", use_container_width=True, type="primary"):
        with st.spinner("Executing end-to-end audit across inbox dataset..."):
            os.system("python main.py")
            st.cache_data.clear()
            st.success("Pipeline execution completed!")
            st.rerun()


# --- HEADER HERO ---
st.title("🚢 SDOC - Automated Shipping Document Auditor")
st.markdown("""
Real-time AI verification engine for parsing multi-channel logistics emails, extracting Shipping Instructions (SI) 
and draft Bills of Lading (BL), auditing field-level discrepancies, and escalating edge cases.
""")

# Load submission dataset
data = load_submission_data()

if not data:
    st.warning("⚠️ No submission results found (`submission.json`). Run `python main.py` or click 'Execute Audit Pipeline' in the sidebar.")
    st.stop()

# --- KPI METRICS ---
df_items = []
for email_id, rec in data.items():
    df_items.append({
        "Email ID": email_id,
        "Category": rec.get("category", "GENERAL"),
        "Status": rec.get("status", "OK"),
        "Review Reason": rec.get("review_reason") or "N/A",
        "Has Defect": rec.get("has_defect", False),
        "Defect Count": len(rec.get("defect_fields", [])),
        "Defect Fields": ", ".join(rec.get("defect_fields", [])) if rec.get("defect_fields") else "None"
    })

df = pd.DataFrame(df_items)
total_emails = len(df)
ok_count = len(df[df["Status"] == "OK"])
mismatch_count = len(df[df["Status"] == "MISMATCH"])
review_count = len(df[df["Status"] == "NEEDS_REVIEW"])

m1, m2, m3, m4 = st.columns(4)
m1.metric("Total Emails Audited", total_emails)
m2.metric("Automated Pass (OK)", f"{ok_count} ({ok_count/total_emails*100:.1f}%)" if total_emails else "0")
m3.metric("Discrepancies (MISMATCH)", f"{mismatch_count} ({mismatch_count/total_emails*100:.1f}%)" if total_emails else "0")
m4.metric("Human Escalations", f"{review_count} ({review_count/total_emails*100:.1f}%)" if total_emails else "0")

st.markdown("---")

# --- MAIN WORKSPACE TABS ---
tab1, tab2, tab3 = st.tabs([
    "📊 Executive Audit Summary", 
    "🔍 Document Inspector & Visual Diff", 
    "🚨 Human-in-the-Loop (HITL) Queue"
])

# --- TAB 1: EXECUTIVE AUDIT SUMMARY ---
with tab1:
    st.subheader("Batch Audit Log")

    col_filter1, col_filter2 = st.columns(2)
    with col_filter1:
        cat_filter = st.multiselect("Filter by Category", options=df["Category"].unique(), default=df["Category"].unique())
    with col_filter2:
        status_filter = st.multiselect("Filter by Status", options=df["Status"].unique(), default=df["Status"].unique())

    filtered_df = df[(df["Category"].isin(cat_filter)) & (df["Status"].isin(status_filter))]

    st.dataframe(
        filtered_df,
        use_container_width=True,
        column_config={
            "Email ID": st.column_config.TextColumn("Email ID", width="small"),
            "Category": st.column_config.TextColumn("Category", width="medium"),
            "Status": st.column_config.TextColumn("Audit Status", width="medium"),
            "Review Reason": st.column_config.TextColumn("Escalation Reason", width="medium"),
            "Defect Count": st.column_config.NumberColumn("Defect Count", width="small"),
            "Defect Fields": st.column_config.TextColumn("Mismatched Fields", width="large"),
        },
        hide_index=True
    )

    st.markdown("### Category Distribution")
    cat_counts = df["Category"].value_counts().reset_index()
    cat_counts.columns = ["Category", "Count"]
    st.bar_chart(cat_counts.set_index("Category"))


# --- TAB 2: DOCUMENT INSPECTOR & VISUAL DIFF ---
with tab2:
    st.subheader("Field-Level Discrepancy Inspector")

    selected_id = st.selectbox("Select Email Record to Inspect", options=list(data.keys()))

    if selected_id:
        record = data[selected_id]
        
        c1, c2, c3 = st.columns(3)
        c1.markdown(f"**Category:** `{record.get('category')}`")
        c2.markdown(f"**Status:** {render_status_badge(record.get('status'))}", unsafe_allow_html=True)
        c3.markdown(f"**Escalation Reason:** `{record.get('review_reason') or 'None'}`")

        st.markdown("#### Document Comparison Matrix")

        target_fields = [
            "shipper", "consignee", "notify_party", 
            "port_of_loading", "port_of_discharge", 
            "container_count", "gross_weight_kg"
        ]
        
        defect_fields = record.get("defect_fields", [])
        
        diff_matrix = []
        for field in target_fields:
            is_defect = field in defect_fields
            diff_matrix.append({
                "Field Name": field.replace("_", " ").title(),
                "Shipping Instruction (SI)": "Extracted Value" if not is_defect else "Value A (SI)",
                "Draft Bill of Lading (BL)": "Extracted Value" if not is_defect else "Value B (BL)",
                "Match Status": "❌ MISMATCH" if is_defect else "✅ MATCH"
            })

        st.table(pd.DataFrame(diff_matrix))


# --- TAB 3: HUMAN-IN-THE-LOOP QUEUE ---
with tab3:
    st.subheader("Human Escalation Management")
    
    review_queue = df[df["Status"].isin(["NEEDS_REVIEW", "MISMATCH"])]
    
    if review_queue.empty:
        st.success("🎉 No items requiring human review!")
    else:
        st.info(f"📋 {len(review_queue)} records currently queued for supervisor verification.")
        
        st.dataframe(review_queue[["Email ID", "Category", "Status", "Review Reason", "Defect Fields"]], use_container_width=True)
        
        st.markdown("---")
        st.markdown("### Supervisor Decision Portal")
        
        esc_id = st.selectbox("Select Record for Action", options=review_queue["Email ID"].tolist())
        
        notes = st.text_area("Supervisor Audit Notes", placeholder="Enter notes regarding document validation, manual overrides, or customer outreach...")
        
        col_act1, col_act2 = st.columns(2)
        with col_act1:
            if st.button("✅ Approve Audit Override", use_container_width=True):
                st.success(f"Record `{esc_id}` marked as manually approved.")
        with col_act2:
            if st.button("🚨 Escalate to Carrier", use_container_width=True):
                st.warning(f"Escalation email dispatched for record `{esc_id}`.")