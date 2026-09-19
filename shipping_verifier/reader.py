import os
import pandas as pd

def read_attachment(file_path: str) -> str:
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Attachment file not found: {file_path}")

    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".xlsx":
        excel_data = pd.read_excel(file_path, sheet_name=None)
        output = []
        for sheet_name, df in excel_data.items():
            output.append(f"--- Sheet: {sheet_name} ---")
            output.append(df.to_csv(index=False))
        return "\n".join(output)

    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()