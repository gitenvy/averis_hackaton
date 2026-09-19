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
│                 Groq LPU Acceleration (Dynamic Model Selection)                   │
└─────────────────────────────────────────┬─────────────────────────────────────────┘
                                          │
                                          ▼
                  ┌───────────────────────────────────────────────┐
                  │            Docker Evaluation Server           │
                  │   (FastAPI Service on port 8080 or Tunnel)    │
                  └───────────────────────┴───────────────────────┘
```

1. **Cloud AI Inference Layer**: Powered by **Groq Cloud LPU Infrastructure** for ultra-low latency (~300ms) semantic email classification and multi-modal document entity extraction.
2. **Cloud Application Layer**: Deployed serverless via **Streamlit Cloud** for live batch auditing, manual JSON document inspection, and real-time operational metrics.
3. **Containerized Evaluation Engine**: Local/Cloud REST microservice hosting private evaluation dataset endpoints (`POST /submit`).

---

## 🤖 Groq Model Configuration

The application dynamically selects the Groq LLM model via environment variables (`GROQ_MODEL`), allowing instant model swapping without code changes.

| Model ID | Recommended Use Case | Latency |
| :--- | :--- | :--- |
| `llama-3.3-70b-versatile` | **Default / Production.** Best precision for complex entity extraction & edge cases. | ~500ms |
| `allam-2-7b` | Specialized for Arabic & multilingual logistics text. | ~200ms |
| `llama-3.1-8b-instant` | High-speed classification for high-throughput batching. | ~100ms |
| `mixtral-8x7b-32768` | Long-context handling for dense, multi-page attached spreadsheets. | ~400ms |

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
├── .env                    # Environment key & model storage (Gitignored)
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
* **Node.js / npx** installed (required for port forwarding to Streamlit Cloud)
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
GROQ_MODEL=llama-3.3-70b-versatile
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

## 🖥️ Dashboard UI & Streamlit Deployment

### Option A: Local Dashboard
Run the Streamlit application locally to test both batch auditing and single-file manual JSON inspection:

```bash
streamlit run app.py
```
Access the web dashboard at `http://localhost:8501`.

---

### Option B: Streamlit Cloud Deployment & Port Forwarding

#### 1. Push to GitHub & Deploy
1. Push this repository to GitHub.
2. Log into [share.streamlit.io](https://share.streamlit.io/).
3. Connect your repository and set `app.py` as the main entry point.
4. Under **Advanced Settings -> Secrets**, configure your keys in TOML format:
   ```toml
   GROQ_API_KEY = "gsk_your_actual_groq_api_key_here"
   GROQ_MODEL = "llama-3.3-70b-versatile"
   ```

#### 2. Connect Streamlit Cloud to Local Docker Server via Localtunnel (`npx`)
Because Streamlit Cloud runs on a public server, it cannot reach `http://localhost:8080` on your machine directly. To run public batch audits against your local Docker evaluation server, expose port `8080`:

1. Keep your Docker server running on port `8080` (`docker compose up`).
2. Open a new terminal and run Localtunnel via `npx`:
   ```powershell
   # Bypass execution restriction in Windows PowerShell if required:
   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

   # Launch public port forwarding tunnel for port 8080:
   npx localtunnel --port 8080
   ```
3. Copy the generated public URL (e.g., `https://neat-lions-jump.loca.lt`).
4. Paste the public URL into the **Evaluation Server URL** text box in the Streamlit Cloud sidebar and click **▶️ Run Pipeline Audit**.

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
# Re-run pipeline locally
python main.py

# Expose Docker server port to external/cloud services
npx localtunnel --port 8080
```

### Common Pitfalls
1. **Missing `.env` File**: Ensure `.env` is created locally in the root directory containing `GROQ_API_KEY` and `GROQ_MODEL`.
2. **Docker Connection Error**: Verify Docker Desktop is active and running `docker compose up` inside `data_averis`.
3. **Streamlit Cloud Localhost Error**: Do not use `http://localhost:8080` inside the public Streamlit Cloud interface. Use **Tab 2 (Single File Inspection)** or set up `npx localtunnel --port 8080` to pass the public URL.