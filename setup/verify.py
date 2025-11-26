from sqlalchemy import create_engine, text

# ==============================
# CONFIG
# ==============================

AURORA_HOST = "amg-traffic-cluster.cluster-clss68yoix1c.us-east-2.rds.amazonaws.com"
AURORA_DB = "postgres"
DB_USER = "root"
DB_PASS = "rootroot"
DB_PORT = 5432

# ==============================
# CONNECT AND VERIFY
# ==============================

print("Conectando a Aurora...")
engine = create_engine(
    f"postgresql://{DB_USER}:{DB_PASS}@{AURORA_HOST}:{DB_PORT}/{AURORA_DB}?sslmode=require"
)

print("Verificando cantidad de registros en traffic_data...\n")

with engine.connect() as conn:
    result = conn.execute(text("SELECT COUNT(*) FROM traffic_data"))
    count = result.fetchone()[0]
    
    print("=" * 50)
    print(f"Total de registros en traffic_data: {count:,}")
    print("=" * 50)
