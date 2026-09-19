import os
import sys
import json
import streamlit as st

# 1. Path Resolution for loader.py inside data_averis/server
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(BASE_DIR, "data_averis"))
sys.path.append(os.path.join(BASE_DIR, "data_averis", "server"))

# Load Groq API Key from Streamlit Secrets or Environment
groq_key = None
if "GROQ_API_KEY" in st.secrets:
    groq_key = st.secrets["GROQ_API_KEY"]
    os.environ["GROQ_API_KEY"] = groq_key
elif os.getenv("GROQ_API_KEY"):
    groq_key = os.getenv("GROQ_API_KEY")

# Safe Imports with Default Unbound Prevention
Inbox = None
try:
    from loader import Inbox
except ImportError:
    try:
        from data_averis.server.loader import Inbox
    except ImportError:
        Inbox = None

process_email = None
try:
    from main import process_email
except ImportError as e:
    st.error(f"Error importing process_email from main.py: {e}")


# 2. Streamlit Page Configuration
st.set_page_config(
    page_title="SDOC Shipping Document Auditor",
    page_icon="🚢",
    layout="wide"
)

st.title("🚢 SDOC Automated Shipping Document Auditor")
st.caption("Cloud-Native AI Document Audit & Verification Engine Powered by Groq LPU Cloud & Allam-2-7B")

# API Key Check Banner
if not groq_key:
    st.warning("⚠️ GROQ_API_KEY not detected in secrets or environment. Configure it under Streamlit Cloud Advanced Settings.")

st.markdown("---")

# 3. Sidebar Configuration
st.sidebar.header("⚙️ Configuration")
server_url = st.sidebar.text_input("Evaluation Server URL", value="http://localhost:8080")
sample_limit = st.sidebar.slider("Sample size for batch run", min_value=1, max_value=520, value=20)

st.sidebar.markdown("""
### ☁️ Cloud Architecture
- **Inference**: Groq Cloud LPU
- **Model**: `Allam-2-7B`
- **Frontend**: Streamlit Cloud
- **Pipeline**: Decoupled Python REST Service
""")


# 4. Main UI Tabs
tab1, tab2 = st.tabs(["🚀 Server Audit Runner", "📄 Single File Inspection"])

with tab1:
    st.subheader("Batch Evaluation Runner")
    st.write("Run the cloud AI pipeline against the evaluation server inbox.")

    if st.button("▶️ Run Pipeline Audit", type="primary"):
        if not Inbox:
            st.error("Could not load `Inbox` class. Please check your repository folder structure.")
        elif not process_email:
            st.error("Could not load `process_email` function from `main.py`.")
        else:
            with st.spinner("Connecting to server & running Groq LPU Cloud extraction..."):
                try:
                    inbox = Inbox(server_url)
                    emails = list(inbox)[:sample_limit]
                    
                    results = {}
                    progress_bar = st.progress(0)
                    
                    for i, email in enumerate(emails):
                        eid = email.get("email_id") or email.get("id") or f"email_{i+1:03d}"
                        results[str(eid)] = process_email(email, inbox)
                        progress_bar.progress((i + 1) / len(emails))

                    st.success(f"Successfully processed {len(results)} emails!")

                    # Summary Metrics Dashboard
                    col1, col2, col3, col4 = st.columns(4)
                    
                    categories = [r["category"] for r in results.values()]
                    bl_comp = sum(1 for c in categories if c == "BL_COMPARISON")
                    mismatches = sum(1 for r in results.values() if r.get("status") == "MISMATCH")
                    needs_review = sum(1 for r in results.values() if r.get("status") == "NEEDS_REVIEW")

                    col1.metric("Total Evaluated", len(results))
                    col2.metric("BL Comparisons", bl_comp)
                    col3.metric("Defects / Mismatches", mismatches)
                    col4.metric("Needs Review", needs_review)

                    st.subheader("Submission Payload Output (`submission.json`)")
                    st.json(results)

                except Exception as e:
                    st.error(f"Execution error: {e}")
                    st.info("Note: When deployed publicly on Streamlit Cloud, localhost endpoints (http://localhost:8080) must be replaced with a public server URL or tested using Tab 2.")

with tab2:
    st.subheader("Manual Email JSON Upload & Inspection")
    st.write("Upload a raw email JSON object to inspect the classification and discrepancy detection live.")
    
    uploaded_file = st.file_uploader("Upload email JSON file", type=["json"])
    
    if uploaded_file is not None:
        try:
            email_data = json.load(uploaded_file)
            
            col_a, col_b = st.columns(2)
            
            with col_a:
                st.subheader("Input Email Payload")
                st.json(email_data)

            with col_b:
                st.subheader("AI Pipeline Result")
                if st.button("Run Audit on Uploaded Email"):
                    if not process_email:
                        st.error("`process_email` could not be loaded from `main.py`.")
                    elif not Inbox:
                        st.error("`Inbox` class could not be loaded from `loader.py`.")
                    else:
                        with st.spinner("Analyzing document with Allam-2-7B..."):
                            inbox_instance = Inbox(server_url)
                            result = process_email(email_data, inbox_instance)
                            st.json(result)
                            
                            if result.get("status") == "MISMATCH":
                                st.error(f"Mismatches Found: {result.get('defect_fields')}")
                            elif result.get("status") == "NEEDS_REVIEW":
                                st.warning(f"Escalated to Human Review: {result.get('review_reason')}")
                            else:
                                st.success("All fields match specifications!")

        except Exception as e:
            st.error(f"Error parsing uploaded file: {e}")