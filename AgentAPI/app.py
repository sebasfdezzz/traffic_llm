import json
from flask import Flask, render_template, request, jsonify
from sqlalchemy import create_engine, text
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import create_sql_agent
from langchain_openai import ChatOpenAI
from geopy.geocoders import Nominatim

AURORA_HOST = "amg-traffic-cluster.cluster-clss68yoix1c.us-east-2.rds.amazonaws.com"
AURORA_DB = "postgres"
DB_USER = "root"
DB_PASS = "rootroot"
DB_PORT = 5432
OPENAI_API_KEY = "<INSERT_KEY>"

app = Flask(__name__)

print("🚀 Initializing AMG Traffic Data Assistant...")

print(f"📊 Connecting to database: {AURORA_HOST}")
engine = create_engine(
    f"postgresql://{DB_USER}:{DB_PASS}@{AURORA_HOST}:{DB_PORT}/{AURORA_DB}?sslmode=require",
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10
)
print("✅ Database engine created")

db = SQLDatabase(engine)
print("✅ SQL Database wrapper initialized")

print("🤖 Setting up LLM agent with OpenAI...")
llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0,
    openai_api_key=OPENAI_API_KEY
)

agent_executor = create_sql_agent(
    llm=llm,
    db=db,
    agent_type="openai-tools",
    verbose=True,
    max_iterations=10,
    handle_parsing_errors=True
)
print("✅ LLM agent ready")

print("🗺️  Setting up geocoding service...")
geolocator = Nominatim(user_agent="amg_traffic_app")
print("✅ Geocoder ready")

def get_address_from_coordinates(lat, lon):
    try:
        location = geolocator.reverse(f"{lat}, {lon}", language="es", timeout=10)
        if location:
            address = location.raw.get('address', {})
            
            parts = []
            if 'road' in address:
                parts.append(address['road'])
            if 'suburb' in address:
                parts.append(address['suburb'])
            elif 'neighbourhood' in address:
                parts.append(address['neighbourhood'])
            if 'city' in address:
                parts.append(address['city'])
            elif 'town' in address:
                parts.append(address['town'])
            
            return ', '.join(parts) if parts else location.address
        return None
    except Exception as e:
        print(f"Geocoding error: {e}")
        return None

def get_coordinates_from_address(address_query):
    try:
        location = geolocator.geocode(address_query, timeout=10)
        if location:
            return (location.latitude, location.longitude)
        return None
    except Exception as e:
        print(f"Forward geocoding error: {e}")
        return None

def detect_and_convert_address_in_question(question):
    address_keywords = [
        'street', 'avenue', 'road', 'calle', 'avenida', 'en ', 'on ',
        'boulevard', 'bulevar', 'callejón', 'callejuela', 'paseo',
        'plaza', 'plazuela', 'glorieta', 'rotonda', 'circuito',
        'periférico', 'anillo', 'libramiento', 'autopista',
        'carretera', 'camino', 'sendero', 'vereda', 'andador',
        'privada', 'fraccionamiento', 'colonia', 'barrio',
        'sector', 'zona', 'región', 'área', 'distrito',
        'cerca de', 'próximo a', 'junto a', 'frente a',
        'esquina', 'cruce', 'intersección', 'puente',
        'centro comercial', 'mall', 'mercado', 'hospital',
        'escuela', 'universidad', 'parque', 'jardín'
    ]
    
    lower_question = question.lower()
    has_address_keyword = any(keyword in lower_question for keyword in address_keywords)
    
    if has_address_keyword:
        coords = get_coordinates_from_address(question)
        
        if coords:
            lat, lon = coords
            return f"{question}\n\nNOTA: La dirección corresponde aproximadamente a latitud {lat} y longitud {lon}. Busca datos de tráfico con coordx cerca de {lat} y coordy cerca de {lon} (dentro de un radio de 0.01 grados)."
    
    return question

def enrich_results_with_addresses(query_result):
    try:
        if isinstance(query_result, str):
            return query_result
        
        if isinstance(query_result, list):
            for record in query_result:
                if isinstance(record, dict) and 'coordx' in record and 'coordy' in record:
                    address = get_address_from_coordinates(record['coordx'], record['coordy'])
                    if address:
                        record['address'] = address
        
        return query_result
    except Exception as e:
        print(f"Error enriching results: {e}")
        return query_result

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/ask', methods=['POST'])
def ask_question():
    try:
        data = request.get_json()
        question = data.get('question', '').strip()
        
        print(f"\n{'='*60}")
        print(f"📥 New question received: '{question}'")
        print(f"{'='*60}")
        
        if not question:
            print("❌ Empty question received")
            return jsonify({'error': 'No se proporcionó ninguna pregunta'}), 400
        
        print("🔍 Checking for address in question...")
        question_with_coords = detect_and_convert_address_in_question(question)
        if question_with_coords != question:
            print("✅ Address detected and converted to coordinates")
        else:
            print("ℹ️  No address detected, proceeding with original question")
        
        enhanced_question = f"""
        Estás analizando datos de tráfico del Área Metropolitana de Guadalajara (AMG), México.
        
        Tienes acceso a una tabla llamada 'traffic_data' con estas columnas:
        - id (TEXT): identificador único de la ubicación
        - predominant_color (TEXT): indicador de nivel de tráfico
          * green = tráfico LIGERO (fluido, sin congestión)
          * yellow/orange = tráfico MEDIO (algo de congestión)
          * red = tráfico ALTO (congestión severa, muy lento)
        - exponential_color_weighting (FLOAT): puntaje de congestión ponderado exponencial (mayor valor = peor tráfico)
        - linear_color_weighting (FLOAT): puntaje de congestión ponderado lineal (mayor valor = peor tráfico)
        - diffuse_logic_traffic (FLOAT): valor difuso (NO es relevante, ignóralo)
        - coordx (FLOAT): coordenada de LONGITUD (aproximadamente -103.2 a -103.5 para Guadalajara)
        - coordy (FLOAT): coordenada de LATITUD (aproximadamente 20.5 a 20.8 para Guadalajara)
        
        IMPORTANTE: Las coordenadas están en formato (longitud, latitud). Coordx es longitud (oeste de Greenwich, valores negativos) y Coordy es latitud.
        
        Pregunta del usuario: {question_with_coords}
        
        Al buscar por coordenadas, usa una consulta de rango como: WHERE coordx BETWEEN (lon-0.01) AND (lon+0.01) AND coordy BETWEEN (lat-0.01) AND (lat+0.01)
        
        Por favor proporciona una respuesta clara y concisa en español. Si devuelves datos con coordenadas, incluye los valores de coordx y coordy.
        Cuando menciones niveles de tráfico, usa términos claros: tráfico ligero/fluido (green), tráfico medio (yellow/orange), tráfico pesado/alto (red).
        """
        
        print("🤖 Executing SQL agent...")
        result = agent_executor.invoke({"input": enhanced_question})
        print("✅ Agent execution completed")
        
        answer = result.get('output', 'No se generó respuesta')
        print(f"📝 Answer generated: {answer[:100]}..." if len(answer) > 100 else f"📝 Answer: {answer}")
        
        print(f"✅ Request processed successfully")
        print(f"{'='*60}\n")
        return jsonify({
            'answer': answer,
            'success': True
        })
        
    except Exception as e:
        print(f"\n❌ ERROR processing question: {e}")
        print(f"{'='*60}\n")
        return jsonify({
            'error': f'Error al procesar tu pregunta: {str(e)}',
            'success': False
        }), 500

@app.route('/health', methods=['GET'])
def health_check():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        
        return jsonify({
            'status': 'healthy',
            'database': 'connected'
        })
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 500

@app.route('/table-info', methods=['GET'])
def table_info():
    try:
        with engine.connect() as conn:
            count_result = conn.execute(text("SELECT COUNT(*) FROM traffic_data")).fetchone()
            
            sample_result = conn.execute(text(
                "SELECT * FROM traffic_data LIMIT 5"
            )).fetchall()
            
            columns_result = conn.execute(text("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'traffic_data'
            """)).fetchall()
            
            return jsonify({
                'total_records': count_result[0],
                'columns': [{'name': col[0], 'type': col[1]} for col in columns_result],
                'sample_data': [dict(row._mapping) for row in sample_result]
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("\n" + "="*60)
    print("🚦 AMG Traffic Data Assistant is ready!")
    print("🌐 Server starting on http://0.0.0.0:80")
    print("="*60 + "\n")
    app.run(host='0.0.0.0', port=80, debug=False)
