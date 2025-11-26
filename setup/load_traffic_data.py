import os
import subprocess
import glob
import pandas as pd
from tqdm import tqdm
import boto3

# ==============================
# CONFIG
# ==============================

BUCKET = "amg-traffic-data"
S3_KEY = "unificado/amg_traffic_2024_2025.csv"

# ==============================
# STEP 1 — clone repos
# ==============================

print("Clonando repositorios...")
if not os.path.exists("AMGtraffic2025"):
    subprocess.run(["git", "clone", "https://github.com/ralejandrobm/AMGtraffic2025.git"])

if not os.path.exists("AMGTraffic2024"):
    subprocess.run(["git", "clone", "https://github.com/ralejandrobm/AMGTraffic2024.git"])

# ==============================
# STEP 2 — cargar csvs
# ==============================

print("Leyendo CSVs 2025...")
files_2025 = glob.glob("AMGtraffic2025/historico/*.csv")

print("Leyendo CSVs 2024...")
files_2024 = glob.glob("AMGTraffic2024/historico/*.csv")

dfs = []

print("Cargando archivos y concatenando...")
for f in tqdm(files_2025 + files_2024):
    df = pd.read_csv(f)
    dfs.append(df)

full_df = pd.concat(dfs, ignore_index=True)

print("Leyendo locationPoints.csv...")
loc = pd.read_csv(
    "AMGtraffic2025/locationPoints.csv",
    encoding="latin1",
    on_bad_lines="skip",
    engine="python"
)

print("Unificando tablas por id...")
merged = full_df.merge(loc, on="id", how="left")

# ==============================
# STEP 3 — guardar CSV temporal
# ==============================

out_file = "amg_unificado.csv"
merged.to_csv(out_file, index=False)

print(f"Archivo unificado generado: {out_file}")

# ==============================
# STEP 4 — subir a S3
# ==============================

print("Subiendo a S3...")
s3 = boto3.client("s3")
s3.upload_file(out_file, BUCKET, S3_KEY)

print(f"✓ Subido a s3://{BUCKET}/{S3_KEY}")

print("\n========== RESUMEN ==========")
print(f"Total registros: {len(merged):,}")
print(f"Archivo S3: s3://{BUCKET}/{S3_KEY}")
print("=============================")
