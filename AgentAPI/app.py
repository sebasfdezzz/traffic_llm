import json
from flask import Flask, render_template, request, jsonify
from sqlalchemy import create_engine, text
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import create_sql_agent
from langchain_openai import ChatOpenAI
from geopy.geocoders import Nominatim

# ==============================
# CONFIG
# ==============================

AURORA_HOST = "amg-traffic-cluster.cluster-clss68yoix1c.us-east-2.rds.amazonaws.com"
AURORA_DB = "postgres"
DB_USER = "root"
DB_PASS = "rootroot"
DB_PORT = 5432
OPENAI_API_KEY = "<INSERT_KEY>"

# Initialize Flask app
app = Flask(__name__)

print("🚀 Initializing AMG Traffic Data Assistant...")

# ==============================
# DATABASE CONNECTION
# ==============================

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

# ==============================
# LLM AGENT SETUP
# ==============================

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

# ==============================
# GEOCODING SETUP
# ==============================

print("🗺️  Setting up geocoding service...")
geolocator = Nominatim(user_agent="amg_traffic_app")
print("✅ Geocoder ready")

def get_address_from_coordinates(lat, lon):
    """
    Get street name or area from coordinates using reverse geocoding.
    """
    try:
        location = geolocator.reverse(f"{lat}, {lon}", language="es", timeout=10)
        if location:
            address = location.raw.get('address', {})
            
            # Try to build a meaningful address
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
    """
    Get coordinates from street name/address using forward geocoding.
    Returns tuple (lat, lon) or None if not found.
    """
    try:
        location = geolocator.geocode(address_query, timeout=10)
        if location:
            return (location.latitude, location.longitude)
        return None
    except Exception as e:
        print(f"Forward geocoding error: {e}")
        return None

def detect_and_convert_address_in_question(question):
    """
    Detect if the question contains a street name or address and convert it to coordinates.
    Returns enhanced question with coordinate information.
    """
    # Common patterns that suggest an address query
    address_keywords = ['street', 'avenue', 'road', 'calle', 'avenida', 'en ', 'on ']
    
    # Check if question likely contains an address
    lower_question = question.lower()
    has_address_keyword = any(keyword in lower_question for keyword in address_keywords)
    
    if has_address_keyword:
        # Try to geocode the question as-is or extract the address part
        coords = get_coordinates_from_address(question)
        
        if coords:
            lat, lon = coords
            # Add coordinate info to help the SQL agent
            return f"{question}\n\nNOTE: The address corresponds to approximately latitude {lat} and longitude {lon}. Search for traffic data with coordx near {lat} and coordy near {lon} (within 0.01 degree radius)."
    
    return question

def enrich_results_with_addresses(query_result):
    """
    If the result contains coordinates, add address information.
    """
    try:
        # Check if result contains coordinate data
        if isinstance(query_result, str):
            return query_result
        
        # If it's a list of records with Coordx and Coordy
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

# ==============================
# ROUTES
# ==============================

@app.route('/')
def index():
    """Render the main UI."""
    return render_template('index.html')

@app.route('/ask', methods=['POST'])
def ask_question():
    """
    Process natural language questions about traffic data.
    """
    try:
        data = request.get_json()
        question = data.get('question', '').strip()
        
        print(f"\n{'='*60}")
        print(f"📥 New question received: '{question}'")
        print(f"{'='*60}")
        
        if not question:
            print("❌ Empty question received")
            return jsonify({'error': 'No se proporcionó ninguna pregunta'}), 400
        
        # Detect and convert address to coordinates if needed
        print("🔍 Checking for address in question...")
        question_with_coords = detect_and_convert_address_in_question(question)
        if question_with_coords != question:
            print("✅ Address detected and converted to coordinates")
        else:
            print("ℹ️  No address detected, proceeding with original question")
        
        # Add context to help the agent understand the data structure
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
        
        # Execute the agent
        print("🤖 Executing SQL agent...")
        result = agent_executor.invoke({"input": enhanced_question})
        print("✅ Agent execution completed")
        
        answer = result.get('output', 'No se generó respuesta')
        print(f"📝 Answer generated: {answer[:100]}..." if len(answer) > 100 else f"📝 Answer: {answer}")
        
        # Try to extract coordinates from the intermediate steps and enrich with addresses
        enriched_answer = answer
        try:
            # Check if there are coordinates in the result
            if 'coordx' in answer.lower() or 'coordy' in answer.lower():
                print("🗺️  Coordinates found in answer, enriching with addresses...")
                # Try to extract coordinates and get addresses
                # This is a simple implementation - can be enhanced
                with engine.connect() as conn:
                    # Get a sample of results if the query was about specific locations
                    query_result = conn.execute(text(
                        "SELECT id, predominant_color, coordx, coordy FROM traffic_data LIMIT 5"
                    )).fetchall()
                    
                    if query_result:
                        addresses = []
                        for row in query_result:
                            addr = get_address_from_coordinates(row[2], row[3])
                            if addr:
                                addresses.append(f"ID {row[0]} ({row[1]}): {addr}")
                        
                        if addresses:
                            print(f"✅ Added {len(addresses)} address(es) to response")
                            enriched_answer += "\n\nUbicaciones:\n" + "\n".join(addresses)
        except Exception as e:
            print(f"⚠️  Error adding addresses: {e}")
        
        print(f"✅ Request processed successfully")
        print(f"{'='*60}\n")
        return jsonify({
            'answer': enriched_answer,
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
    """Health check endpoint."""
    try:
        # Test database connection
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
    """Get information about the traffic_data table."""
    try:
        with engine.connect() as conn:
            # Get row count
            count_result = conn.execute(text("SELECT COUNT(*) FROM traffic_data")).fetchone()
            
            # Get sample data
            sample_result = conn.execute(text(
                "SELECT * FROM traffic_data LIMIT 5"
            )).fetchall()
            
            # Get column names
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

# ==============================
# RUN
# ==============================

if __name__ == '__main__':
    # For production on EC2, use a proper WSGI server like gunicorn
    # This is for development only
    print("\n" + "="*60)
    print("🚦 AMG Traffic Data Assistant is ready!")
    print("🌐 Server starting on http://0.0.0.0:80")
    print("="*60 + "\n")
    app.run(host='0.0.0.0', port=80, debug=False)
