from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy import create_engine
from langchain.chains import SQLDatabaseChain
from langchain.sql_database import SQLDatabase
from langchain.llms import OpenAI  # si usarás OpenAI; más abajo pongo Bedrock

# =====================
# CONFIG
# =====================

AURORA_HOST = "<AURORA-ENDPOINT>"
DB_USER = "postgres"
DB_PASS = "<PASSWORD>"
DB_NAME = "postgres"

engine = create_engine(
    f"postgresql://{DB_USER}:{DB_PASS}@{AURORA_HOST}:5432/{DB_NAME}"
)

db = SQLDatabase(engine)

llm = OpenAI(
    temperature=0,
    model="gpt-4.1-mini"   # o el que prefieras
)

chain = SQLDatabaseChain.from_llm(llm, db, verbose=True)

app = FastAPI()

class Query(BaseModel):
    question: str

@app.post("/ask")
def ask(q: Query):
    answer = chain.run(q.question)
    return {"answer": answer}
