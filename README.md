# 🚢 Automated Shipping Document Auditor

An enterprise-grade AI verification pipeline and Human-in-the-Loop (HITL) auditing dashboard designed to streamline logistics communications, cross-examine Shipping Instructions (SI) against Bills of Lading (BL), and automatically flag operational discrepancies or edge cases.

---

## 🌟 Key Features

* **Hybrid Email Intent Classification**: Automatically categorizes incoming logistics communications into `BL_COMPARISON`, `SI_REQUEST`, `INVOICE_QUERY`, `GENERAL`, or `SPAM`.
* **Multi-Format Attachment Extraction**: Reads and parses structured data across plain text, PDF, Word (`.docx`), and Excel (`.xlsx`) files.
* **Unit & String Normalization**:
  * **Weight Normalization**: Automatically converts Metric Tons (MT) to Kilograms (KG) with a 1 kg rounding tolerance to eliminate false mismatches.
  * **Order-Insensitive Token Matching**: Strips punctuation and matches address, port, and company name tokens regardless of minor formatting variations.
* **Field-Level Discrepancy Auditing**: Compares 7 canonical shipment fields:
  * `shipper`
  * `consignee`
  * `notify_party`
  * `port_of_loading`
  * `port_of_discharge`
  * `container_count`
  * `gross_weight_kg`
* **Automated Escalation Management**: Escalates unreadable files, missing attachments, incorrect document types, or placeholder values to `NEEDS_REVIEW` status.
* **Interactive HITL Dashboard**: Built with Streamlit, providing an Executive Summary, Document Diff Inspector, and Supervisor Action Portal with session-persistent overrides.
* **Plug-and-Play Offline Execution**: Automatically detects and falls back to local dataset directories (`offline_inbox/` or `data_averis/`) when an active evaluation server is offline.

---

## 🏗️ Architecture & Pipeline Flow

```text
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
