import os
import boto3
import pandas as pd
from sqlalchemy import create_engine, text
from tqdm import tqdm
from io import StringIO

BUCKET = "amg-traffic-data"
S3_KEY = "unificado/amg_traffic_2024_2025.csv"
AURORA_HOST = "amg-traffic-cluster.cluster-clss68yoix1c.us-east-2.rds.amazonaws.com"
AURORA_DB = "postgres"
DB_USER = "root"
DB_PASS = "rootroot"
DB_PORT = 5432

print(f"Descargando archivo desde s3://{BUCKET}/{S3_KEY}...")
s3 = boto3.client("s3")

local_file = "temp_s3_download.csv"
s3.download_file(BUCKET, S3_KEY, local_file)
print(f"✓ Archivo descargado: {local_file}")

print("Leyendo CSV...")
df = pd.read_csv(local_file)
print(f"✓ Cargados {len(df):,} registros")

print("Conectando a Aurora...")
engine = create_engine(
    f"postgresql://{DB_USER}:{DB_PASS}@{AURORA_HOST}:{DB_PORT}/{AURORA_DB}?sslmode=require"
)

print("Creando tabla traffic_data si no existe...")

create_table_sql = """
CREATE TABLE IF NOT EXISTS traffic_data (
    id TEXT,
    predominant_color TEXT,
    exponential_color_weighting FLOAT,
    linear_color_weighting FLOAT,
    diffuse_logic_traffic FLOAT,
    Coordx FLOAT,
    Coordy FLOAT
);
"""

with engine.connect() as conn:
    conn.execute(text(create_table_sql))
    conn.commit()

print("✓ Tabla lista")

print("Normalizando columnas numéricas...")

cols_float = [
    "exponential_color_weighting",
    "linear_color_weighting",
    "diffuse_logic_traffic",
    "Coordx",
    "Coordy",
]

for c in cols_float:
    df[c] = pd.to_numeric(df[c], errors="coerce")

print("✓ Columnas numéricas normalizadas (errores → NULL)")


print("Insertando datos con método COPY (ultra rápido)...")

csv_buffer = StringIO()
df.to_csv(csv_buffer, index=False, header=False)
csv_buffer.seek(0)

copy_sql = """
COPY traffic_data (
    id,
    predominant_color,
    exponential_color_weighting,
    linear_color_weighting,
    diffuse_logic_traffic,
    Coordx,
    Coordy
)
FROM STDIN WITH CSV;
"""

conn = engine.raw_connection()
cursor = conn.cursor()

try:
    cursor.copy_expert(copy_sql, csv_buffer)
    conn.commit()
    print("✓ CARGA COMPLETA A AURORA (COPY METHOD)")

except Exception as e:
    conn.rollback()
    print("ERROR en COPY:", e)

finally:
    cursor.close()
    conn.close()

print("Limpiando archivo temporal...")
os.remove(local_file)
print("✓ Archivo temporal eliminado")

print("\nVerificando primeros registros...")

with engine.connect() as conn:
    rows = conn.execute(text("SELECT * FROM traffic_data LIMIT 20")).fetchall()

    print(f"✓ Primeros {len(rows)} registros:")
    for r in rows:
        print(r)

print("\n=========== FIN ===========")
print(f"Registros cargados: {len(df):,}")
print("===========================")
