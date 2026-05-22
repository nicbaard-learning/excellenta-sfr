import openpyxl
import pandas as pd

# Path to your SCF workbook
workbook_path = "secure-controls-framework-scf-2026-1.xlsx"

# Try to load the main SCF sheet
try:
    wb = openpyxl.load_workbook(workbook_path, data_only=True, read_only=False)
except Exception as e:
    print(f"Failed to open workbook: {e}")
    exit(1)

# Try to find the main sheet
sheet_name = None
for name in wb.sheetnames:
    if "scf 2026" in name.lower():
        sheet_name = name
        break
if not sheet_name:
    print("No SCF 2026 sheet found!")
    exit(1)

# Load with pandas for easier column handling
df = pd.read_excel(workbook_path, sheet_name=sheet_name, engine="openpyxl")

# Normalize headers
def normalize_headers(headers):
    return [str(h).strip().replace("\n", " ").replace("\r", "") for h in headers]

headers = normalize_headers(df.columns)

# Find NIST 800-63 column (IAM mapping)
found = False
for idx, h in enumerate(headers):
    if "nist 800-63" in h.lower():
        print(f"Found IAM framework column: {h}")
        found = True
        # Show a sample of mapped controls
        col = df.columns[idx]
        mapped = df[[col]].dropna()
        print(f"Sample mapped values (first 10):\n{mapped.head(10)}")
        break
if not found:
    print("No NIST 800-63 (IAM) column found in SCF sheet.")
