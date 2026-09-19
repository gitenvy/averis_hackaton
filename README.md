# 🚢 SDOC - Automated Shipping Document Auditor

An enterprise-grade, AI-powered document verification pipeline and audit engine built for the **SDOC Hackathon**. 

This solution automatically parses multi-channel logistics emails, classifies intent, extracts key entities from attached Shipping Instructions (SI) and Bills of Lading (BL), detects field-level discrepancies, and routes edge cases for human review.

---

## ☁️ System Architecture & Cloud Integration

The solution is architected around a decoupled **3-Tier Cloud Architecture** utilizing OpenRouter LLM routing and serverless hosting:

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
│                  OpenRouter API (Dynamic Multi-Provider Selection)                │
└─────────────────────────────────────────┬─────────────────────────────────────────┘
                                          │
                                          ▼
                  ┌───────────────────────────────────────────────┐
                  │            Docker Evaluation Server           │
                  │   (FastAPI Service on port 8080 or Tunnel)    │
                  └───────────────────────┴───────────────────────┘
```

1. **Cloud AI Inference Layer**: Powered by **OpenRouter API** for flexible model routing, ultra-low latency semantic email classification, and multi-modal document entity extraction.
2. **Cloud Application Layer**: Deployed serverless via **Streamlit Cloud** for live batch auditing, manual JSON document inspection, and real-time operational metrics.
3. **Containerized Evaluation Engine**: Local/Cloud REST microservice hosting private evaluation dataset endpoints (`POST /submit`).

---

## 🤖 OpenRouter Model Configuration

The application dynamically selects the LLM model via environment variables (`OPENROUTER_MODEL`), allowing instant model swapping without code changes across top provider models.

| Model ID | Recommended Use Case | Latency |
| :--- | :--- | :--- |
| `meta-llama/llama-3.3-70b-instruct` | **Default / Production.** Excellent precision for complex entity extraction & edge cases. | ~500ms |
| `anthropic/claude-3.5-sonnet` | Highest reasoning capability for tricky document formats & noisy text. | ~800ms |
| `deepseek/deepseek-chat` | Highly cost-effective & fast for high-volume batch processing. | ~300ms |
| `qwen/qwen-2.5-72b-instruct` | Strong structured JSON output generation and multilingual support. | ~400ms |

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
* An **OpenRouter API Key** ([Obtain key from OpenRouter Keys Console](https://openrouter.ai/keys))

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
OPENROUTER_API_KEY=sk-or-v1-your_actual_openrouter_api_key_here
OPENROUTER_MODEL=meta-llama/llama-3.3-70b-instruct
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
4. Compare document pairs for discrepancies and flag necessary human review cases (`missing_attachment`, `unreadable`, `wrong_doc_type`, `missing_value`).
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
   OPENROUTER_API_KEY = "sk-or-v1-your_actual_openrouter_api_key_here"
   OPENROUTER_MODEL = "meta-llama/llama-3.3-70b-instruct"
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

### Reliability & Escalation Taxonomy
The `review_reason` parameter must strictly match one of the following canonical error keys when `status == "NEEDS_REVIEW"`:
- `missing_attachment`: Missing required SI or BL attachment files.
- `unreadable`: Corrupted file format, unparseable binary, or failed extraction.
- `wrong_doc_type`: Attached file is not a valid Shipping Instruction or Bill of Lading (e.g., invoice/packing list).
- `missing_value`: Critical target comparison field is missing or null across documents.

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

# Expose Docker server port to external/cloud services
npx localtunnel --port 8080
```

### Common Pitfalls
1. **Missing `.env` File**: Ensure `.env` is created locally in the root directory containing `OPENROUTER_API_KEY` and `OPENROUTER_MODEL`.
2. **Docker Connection Error**: Verify Docker Desktop is active and running `docker compose up` inside `data_averis`.
3. **Streamlit Cloud Localhost Error**: Do not use `http://localhost:8080` inside the public Streamlit Cloud interface. Use **Tab 2 (Single File Inspection)** or set up `npx localtunnel --port 8080` to pass the public URL.