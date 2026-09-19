import streamlit as st
import json
from main import process_email
from loader import Inbox

st.set_page_config(page_title="SDOC Shipping Document Auditor", layout="wide")

st.title("🚢 SDOC Automated Shipping Document Auditor")
st.write("Cloud-Native AI Document Audit & Verification Engine")

# Connect to HTTP / Local Inbox
server_url = st.text_input("Evaluation Server URL", "http://localhost:8080")

if st.button("Run Audit Pipeline"):
    with st.spinner("Processing emails via Groq LPU Cloud..."):
        try:
            inbox = Inbox(server_url)
            emails = list(inbox)
            results = {}
            for email in emails[:10]: # Preview first 10
                eid = email.get("email_id") or email.get("id")
                results[str(eid)] = process_email(email, inbox)
            
            st.success(f"Successfully processed {len(results)} emails!")
            st.json(results)
        except Exception as e:
            st.error(f"Error connecting to server: {e}")