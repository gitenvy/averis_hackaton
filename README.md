Deployement: https://averishackaton-zimjh2yrypszehvbpvhyn3.streamlit.app/

# 🚢 SDOC - Automated Shipping Document Auditor

An enterprise-grade, AI-powered document verification pipeline and audit engine built for the **SDOC Hackathon**. 

This solution automatically parses multi-channel logistics emails, classifies intent, extracts key entities from attached Shipping Instructions (SI) and Bills of Lading (BL), detects field-level discrepancies, and routes edge cases for human review.

---

## ☁️ System Architecture & Cloud Integration

The solution is architected around a decoupled **3-Tier Cloud Architecture** utilizing Groq LPU acceleration and serverless hosting:

```
                  ┌───────────────────────────────────────────────┐
                  │          Streamlit Cloud Frontend             │
                  │        (Public Operational Dashboard)         │
                  └───────────────────────┬───────────────────────┘
                                          │
                                          ▼
                  ┌───────────────────────────────────────────────┐
                  │       Python Orchestration Microservice       │
                  │   (classifier.py, extractor.py, main.py)      │
                  └───────────────────────┬───────────────────────┘
                                          │
                                          ▼
┌─────────────────────────────────────────┴─────────────────────────────────────────┐
│                               Cloud AI Inference Layer                            │
│                       Groq Cloud LPU Allam-2-7B Acceleration                      │
└─────────────────────────────────────────┬─────────────────────────────────────────┘
                                          │
                                          ▼
                  ┌───────────────────────────────────────────────┐
                  │            Docker Evaluation Server           │
                  │         (FastAPI Service on port 8080)        │
                  └───────────────────────────────────────────────┘
```

1. **Cloud AI Inference Layer**: Powered by **Groq Cloud LPU Infrastructure** running `Allam-2-7B` for ultra-low latency (~300ms) semantic email classification and multi-modal document entity extraction.
2. **Cloud Application Layer**: Deployed serverless via **Streamlit Cloud** for live batch auditing, manual JSON document inspection, and real-time operational metrics.
3. **Containerized Evaluation Engine**: Local/Cloud REST microservice hosting private evaluation dataset endpoints (`POST /submit`).

---

## 📁 Repository Structure

```text
shipping_verifier/
├── app.py                  # Streamlit Cloud Dashboard / Web UI
├── main.py                 # Core pipeline orchestration & HTTP submission runner
├── classifier.py           # LLM-powered 5-class intent classifier
├── extractor.py            # Document entity extraction using Pydantic schemas
├── comparator.py           # Field mismatch comparison engine
├── reader.py               # Attachment parser (Text & Excel .xlsx handling)
├── requirements.txt        # Python dependency manifest
├── .env                    # Environment key storage (Gitignored)
└── data_averis/
    └── server/
        ├── app.py          # FastAPI evaluation server
        ├── loader.py       # Data loader client for HTTP / Local datasets
        ├── docker-compose.yml
        └── Dockerfile
```

---

## 🛠️ Setup & Local Installation

### Prerequisites
* **Python 3.10+** installed
* **Docker Desktop** installed and running
* A **Groq API Key** ([Obtain key from Groq Console](https://console.groq.com/))

### 1. Clone & Set Up Virtual Environment

```bash
# Clone the repository
git clone <YOUR_REPOSITORY_URL>
cd shipping_verifier

# Create and activate virtual environment
python -m venv .venv

# PowerShell (Windows):
.\.venv\Scripts\Activate.ps1

# macOS / Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Create a `.env` file in the root `shipping_verifier/` directory:

```env
GROQ_API_KEY=gsk_your_actual_groq_api_key_here
```

---

## 🚀 Running the Evaluation Pipeline

### Step 1: Start the Docker Evaluation Server
Open **Terminal 1**, navigate to `data_averis`, and start the containerized server:

```bash
cd data_averis
docker compose up --build
```
*The evaluation server will listen at `http://localhost:8080`.*

### Step 2: Execute the Main Verification Pipeline
Open **Terminal 2** (from the root directory with `.venv` activated):

```bash
python main.py
```

This will:
1. Fetch evaluation emails from `http://localhost:8080`.
2. Classify intent (`BL_COMPARISON`, `SI_REQUEST`, `INVOICE_QUERY`, `GENERAL`, `SPAM`).
3. Extract shipment details for target fields (`shipper`, `consignee`, `port_of_loading`, `port_of_discharge`, `vessel`, etc.).
4. Compare document pairs for discrepancies and flag necessary human review cases.
5. Save `submission.json` and submit directly to `/submit` for live scoreboard evaluation.

---

## 🖥️ Running the Dashboard UI

### Option A: Local Execution
Run the Streamlit application locally to test both batch auditing and single-file manual JSON inspection:

```bash
streamlit run app.py
```
Access the web dashboard at `http://localhost:8501`.

### Option B: Streamlit Cloud Deployment
1. Push this repository to GitHub.
2. Log into [share.streamlit.io](https://share.streamlit.io/).
3. Connect your repository and set `app.py` as the main entry point.
4. Under **Advanced Settings -> Secrets**, add your Groq key using valid TOML format:
   ```toml
   GROQ_API_KEY = "gsk_your_actual_groq_api_key_here"
   ```

---

## 📊 Evaluation & Submission Format

Submissions are formatted and graded according to the official SDOC specification:

```json
{
  "email_001": {
    "category": "BL_COMPARISON",
    "status": "MISMATCH",
    "review_reason": null,
    "has_defect": true,
    "defect_fields": ["consignee", "port_of_discharge"]
  }
}
```

### Scoring Model Formula
$$\text{Final Score} = 0.30 \times \text{Stage1\_MacroF1} + 0.20 \times \text{Stage3\_DefectF1} + 0.50 \times \text{EndToEnd\_SuccessRate}$$

---

## ⚡ Teammate Onboarding & Troubleshooting

### Fast-Track Commands
```powershell
# Bypasses script execution blocking in Windows PowerShell if needed
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

# Re-run pipeline locally
python main.py
```

### Common Pitfalls
1. **Missing `.env` File**: Ensure `.env` is created locally in the root directory containing `GROQ_API_KEY`.
2. **Docker Connection Error**: Verify Docker Desktop is open and running `docker compose up` inside `data_averis`.
3. **Streamlit Localhost Misalignment**: When accessing the app via public Streamlit Cloud URLs, use **Tab 2 (Single File Inspection)** or expose port `8080` using a tunnel (`npx localtunnel --port 8080`).