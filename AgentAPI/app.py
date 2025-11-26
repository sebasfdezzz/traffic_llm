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

# ==============================
# DATABASE CONNECTION
# ==============================

engine = create_engine(
    f"postgresql://{DB_USER}:{DB_PASS}@{AURORA_HOST}:{DB_PORT}/{AURORA_DB}?sslmode=require",
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10
)

db = SQLDatabase(engine)

# ==============================
# LLM AGENT SETUP
# ==============================

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

# ==============================
# GEOCODING SETUP
# ==============================

geolocator = Nominatim(user_agent="amg_traffic_app")

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
        
        if not question:
            return jsonify({'error': 'No question provided'}), 400
        
        # Add context to help the agent understand the data structure
        enhanced_question = f"""
        You have access to a table called 'traffic_data' with these columns:
        - id (TEXT): unique identifier
        - predominant_color (TEXT): traffic color indicator (red, yellow, green)
        - exponential_color_weighting (FLOAT): exponential weighted traffic score
        - linear_color_weighting (FLOAT): linear weighted traffic score
        - diffuse_logic_traffic (FLOAT): diffuse logic traffic value
        - coordx (FLOAT): latitude coordinate
        - coordy (FLOAT): longitude coordinate
        
        User question: {question}
        
        Please provide a clear, concise answer. If you return data with coordinates, include the coordx and coordy values.
        """
        
        # Execute the agent
        result = agent_executor.invoke({"input": enhanced_question})
        
        answer = result.get('output', 'No answer generated')
        
        # Try to extract coordinates from the intermediate steps and enrich with addresses
        enriched_answer = answer
        try:
            # Check if there are coordinates in the result
            if 'coordx' in answer.lower() or 'coordy' in answer.lower():
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
                            enriched_answer += "\n\nLocations:\n" + "\n".join(addresses)
        except Exception as e:
            print(f"Error adding addresses: {e}")
        
        return jsonify({
            'answer': enriched_answer,
            'success': True
        })
        
    except Exception as e:
        print(f"Error processing question: {e}")
        return jsonify({
            'error': f'Error processing your question: {str(e)}',
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
    app.run(host='0.0.0.0', port=5000, debug=False)
