# Automated Shipping Document Auditor

An enterprise-grade AI verification pipeline and Human-in-the-Loop (HITL) auditing dashboard designed to streamline logistics communications, cross-examine Shipping Instructions (SI) against Bills of Lading (BL), and automatically flag operational discrepancies or edge cases.

---

## Key Features

* Hybrid Email Intent Classification: Automatically categorizes incoming logistics communications into BL_COMPARISON, SI_REQUEST, INVOICE_QUERY, GENERAL, or SPAM.
* Multi-Format Attachment Extraction: Reads and parses structured data across plain text, PDF, Word (.docx), and Excel (.xlsx) files.
* Unit & String Normalization:
  - Weight Normalization: Automatically converts Metric Tons (MT) to Kilograms (KG) with a 1 kg rounding tolerance to eliminate false mismatches.
  - Order-Insensitive Token Matching: Strips punctuation and matches address, port, and company name tokens regardless of minor formatting variations.
* Field-Level Discrepancy Auditing: Compares 7 canonical shipment fields: shipper, consignee, notify_party, port_of_loading, port_of_discharge, container_count, gross_weight_kg.
* Automated Escalation Management: Escalates unreadable files, missing attachments, incorrect document types, or placeholder values to NEEDS_REVIEW status.
* Rate-Limit & Free-Tier Friendly: Built with exponential backoff retries (for HTTP 429 rate limits) and sequential delay pacing to strictly support free-tier LLM API keys.
* Plug-and-Play Offline Execution: Automatically detects and falls back to local dataset directories (offline_inbox/ or data_averis/) when an active evaluation server is offline.
* Interactive HITL Dashboard: Streamlit interface featuring real-time metrics, a field-by-field Document Diff Inspector, and a Supervisor Escalation Portal with session-persistent overrides.

---

## Architecture & Pipeline Flow

[ Incoming Email & Attachments ]
              │
              ▼
    [ Intent Classifier ] ──► (If NOT BL_COMPARISON) ──► Mark Status: OK
              │
              ▼ (If BL_COMPARISON)
   [ Document Parser & Extractor ]
              │
              ├─► Missing Attachments / Unreadable ──► Mark Status: NEEDS_REVIEW
              │
              ▼
  [ Field Comparison Engine ]
  (SI vs BL Cross-Examination)
              │
              ├─► Field Discrepancies Detected ──► Mark Status: MISMATCH (Flag Defect Fields)
              │
              └─► Field Match Verified ─────────► Mark Status: OK

---

## Complete Setup & Installation Guide

### Prerequisites
* Python: 3.10 or higher
* Git: Installed on your system
* API Key: An OpenRouter or Groq API key for LLM inference

---

### Option A: Local Setup

1. Clone the Repository
   git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git
   cd YOUR_REPO

2. Create and Activate a Virtual Environment
   On Windows (PowerShell):
     python -m venv venv
     .\venv\Scripts\Activate.ps1
   On macOS / Linux:
     python3 -m venv venv
     source venv/bin/activate

3. Install Dependencies
   pip install -r requirements.txt

4. Configure Environment Variables
   Create a .env file in the root directory:
     OPENROUTER_API_KEY=your_openrouter_api_key_here
     EVAL_SERVER_URL=http://localhost:8080
     BATCH_LIMIT=20

5. Verify Dataset Placement
   Ensure your offline dataset folder (offline_inbox/ or data_averis/) is present in the project directory. The pipeline will automatically load records from this folder if no active server is detected.

6. Run the Application
   Launch the Interactive Dashboard:
     python -m streamlit run app.py
   Open your browser at http://localhost:8501.

   Run the CLI Pipeline Directly:
     python main.py --limit 20
     python main.py

---

### Option B: Streamlit Cloud Deployment (Zero-Server Plug & Play)

1. Push Code and Offline Inbox to GitHub
   Ensure your local dataset folder (offline_inbox/) is committed to Git so Streamlit Cloud can load files without requiring an external container:
     git add app.py main.py classifier.py extractor.py comparator.py offline_inbox/ requirements.txt
     git commit -m "Configure project for Streamlit Cloud deployment"
     git push origin main

2. Deploy on Streamlit Cloud
   1. Go to share.streamlit.io and log in with GitHub.
   2. Click New app.
   3. Select your Repository, Branch (main), and set Main file path to app.py.
   4. Click Deploy!

3. Add Secrets to Streamlit Cloud
   1. In your deployed app dashboard, click Manage app -> Settings -> Secrets.
   2. Add your keys in TOML format:
      OPENROUTER_API_KEY = "sk-or-v1-your-key-here"
      EVAL_SERVER_URL = "http://localhost:8080"
   3. Click Save. The dashboard will auto-load these credentials upon launch.

---

### Option C: Optional Docker Server Integration

If you are evaluating against an active FastAPI or Docker service endpoint:

1. Launch your container:
   docker run -p 8080:8080 my-eval-server-image

2. Set EVAL_SERVER_URL in .env or in the Streamlit UI to http://localhost:8080 (or your active tunnel URL).
3. The system will automatically run health checks and route requests through the evaluation server.

---

## Streamlit Dashboard Walkthrough

1. Audit Summary & Logs: Interactive KPI cards, searchable logs, category filters, and distribution charts.
2. Document Diff Inspector: Field-by-field comparison matrix cross-examining extracted Shipping Instructions against draft Bills of Lading.
3. Supervisor Escalation Portal: Dedicated Human-in-the-Loop decision console for manual audit overrides, status adjustments, and note logging.

---

## Directory Structure

.
├── app.py                  # Streamlit web dashboard interface
├── main.py                 # Core batch processing pipeline & fallback loader
├── classifier.py           # Email intent classification module
├── extractor.py            # Entity extraction module (SI/BL documents)
├── comparator.py           # Normalization & field comparison engine
├── requirements.txt        # Python dependencies
├── offline_inbox/          # Standalone offline dataset directory
└── submission.json         # Pipeline evaluation output payload
