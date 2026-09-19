import os
import pdfplumber
import docx

def read_attachment(file_path: str) -> str:
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Attachment not found: {file_path}")

    ext = os.path.splitext(file_path)[1].lower()

    if ext in [".txt", ""]:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    elif ext == ".pdf":
        text = ""
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                extracted = page.extract_text()
                if extracted:
                    text += extracted + "\n"
        return text

    elif ext in [".docx", ".doc"]:
        doc = docx.Document(file_path)
        return "\n".join([p.text for p in doc.paragraphs if p.text])

    raise ValueError(f"Unsupported file format: {ext}")