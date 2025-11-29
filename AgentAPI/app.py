import json
import re
import os
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

def obtener_direccion_desde_coordenadas(lat, lon):
    try:
        ubicacion = geolocator.reverse(f"{lat}, {lon}", language="es", timeout=10)
        if ubicacion:
            direccion = ubicacion.raw.get('address', {})
            
            partes = []
            if 'road' in direccion:
                partes.append(direccion['road'])
            if 'suburb' in direccion:
                partes.append(direccion['suburb'])
            elif 'neighbourhood' in direccion:
                partes.append(direccion['neighbourhood'])
            if 'city' in direccion:
                partes.append(direccion['city'])
            elif 'town' in direccion:
                partes.append(direccion['town'])
            
            return ', '.join(partes) if partes else ubicacion.address
        return None
    except Exception as e:
        print(f"Error de geocodificación: {e}")
        return None

def obtener_coordenadas_desde_direccion(consulta_direccion):
    try:
        ubicacion = geolocator.geocode(consulta_direccion, timeout=10)
        if ubicacion:
            return (ubicacion.latitude, ubicacion.longitude)
        return None
    except Exception as e:
        print(f"Error de geocodificación directa: {e}")
        return None

def detectar_y_convertir_direccion_en_pregunta(pregunta):
    palabras_clave_direccion = [
        'calle', 'avenida', 'en ', 'bulevar', 'boulevard',
        'callejón', 'callejuela', 'paseo', 'plaza', 'plazuela',
        'glorieta', 'rotonda', 'circuito', 'periférico', 'anillo',
        'libramiento', 'autopista', 'carretera', 'camino', 'sendero',
        'vereda', 'andador', 'privada', 'fraccionamiento', 'colonia',
        'barrio', 'sector', 'zona', 'región', 'área', 'distrito',
        'cerca de', 'próximo a', 'junto a', 'frente a', 'esquina',
        'cruce', 'intersección', 'puente', 'centro comercial', 'mall',
        'mercado', 'hospital', 'escuela', 'universidad', 'parque', 'jardín'
    ]
    
    pregunta_minusculas = pregunta.lower()
    tiene_palabra_clave_direccion = any(palabra_clave in pregunta_minusculas for palabra_clave in palabras_clave_direccion)
    
    if tiene_palabra_clave_direccion:
        coordenadas = obtener_coordenadas_desde_direccion(pregunta)
        
        if coordenadas:
            lat, lon = coordenadas
            return f"{pregunta}\n\nNOTA: La dirección corresponde aproximadamente a latitud {lat} y longitud {lon}. Busca datos de tráfico con coordx cerca de {lat} y coordy cerca de {lon} (dentro de un radio de 0.01 grados)."
    
    return pregunta

def enriquecer_resultados_con_direcciones(resultado_consulta):
    try:
        if isinstance(resultado_consulta, str):
            return resultado_consulta
        
        if isinstance(resultado_consulta, list):
            for registro in resultado_consulta:
                if isinstance(registro, dict) and 'coordx' in registro and 'coordy' in registro:
                    direccion = obtener_direccion_desde_coordenadas(registro['coordx'], registro['coordy'])
                    if direccion:
                        registro['direccion'] = direccion
        
        return resultado_consulta
    except Exception as e:
        print(f"Error enriqueciendo resultados: {e}")
        return resultado_consulta

def humanizar_respuesta_agente(respuesta_agente):
    """
    Post-procesa la respuesta del agente para convertir coordenadas e IDs técnicos
    a nombres de zonas y direcciones legibles.
    """
    print("🗺️  Humanizando respuesta con nombres de zonas...")
    
    try:
        humanizada = respuesta_agente
        
        # Patrón para detectar coordenadas en varios formatos
        # Formato: "coordx: -103.xxx, coordy: 20.xxx" o "(-103.xxx, 20.xxx)" o "longitud: -103.xxx, latitud: 20.xxx"
        patrones_coordenadas = [
            r'coordx[:\s]+([-\d.]+)[,\s]+coordy[:\s]+([-\d.]+)',
            r'\(([-\d.]+)[,\s]+([-\d.]+)\)',
            r'longitud[:\s]+([-\d.]+)[,\s]+latitud[:\s]+([-\d.]+)',
            r'lon[:\s]+([-\d.]+)[,\s]+lat[:\s]+([-\d.]+)'
        ]
        
        coordenadas_encontradas = set()
        for patron in patrones_coordenadas:
            coincidencias = re.finditer(patron, humanizada, re.IGNORECASE)
            for coincidencia in coincidencias:
                lon = float(coincidencia.group(1))
                lat = float(coincidencia.group(2))
                # Asegurarse de que sean coordenadas válidas para Guadalajara
                if -103.6 < lon < -103.0 and 20.4 < lat < 20.9:
                    coordenadas_encontradas.add((lon, lat, coincidencia.group(0)))
        
        # Convertir cada par de coordenadas a dirección
        reemplazos = {}
        for lon, lat, texto_original in coordenadas_encontradas:
            direccion = obtener_direccion_desde_coordenadas(lat, lon)
            if direccion:
                # Crear una versión humanizada
                texto_zona = f"📍 {direccion}"
                reemplazos[texto_original] = texto_zona
                print(f"   ✅ Traducido: ({lon}, {lat}) -> {direccion}")
        
        # Aplicar reemplazos
        for original, reemplazo in reemplazos.items():
            humanizada = humanizada.replace(original, reemplazo)
        
        # Remover o humanizar IDs técnicos si aparecen explícitamente
        # Patrón para "id: abc123" o "ID: abc123"
        patron_id = r'id[:\s]+[\w-]+'
        coincidencias_id = re.finditer(patron_id, humanizada, re.IGNORECASE)
        for coincidencia in coincidencias_id:
            # Los IDs no son útiles para humanos, intentar removerlos o contextualizarlos
            if "id:" in coincidencia.group(0).lower():
                humanizada = humanizada.replace(coincidencia.group(0), "(ubicación)")
        
        # Mejorar términos técnicos
        reemplazos_tecnicos = {
            'exponential_color_weighting': 'nivel de congestión',
            'linear_color_weighting': 'índice de tráfico',
            'predominant_color': 'estado del tráfico',
            'coordx': 'longitud',
            'coordy': 'latitud',
            'red_wine': '🍷 MUY PESADO (congestión crítica)',
            'green': '🟢 LIGERO (fluido)',
            'yellow': '🟡 MEDIO (moderado)',
            'orange': '🟠 MEDIO-ALTO (algo congestionado)',
            'red': '🔴 PESADO (muy congestionado)'
        }
        
        for termino_tecnico, termino_humano in reemplazos_tecnicos.items():
            humanizada = re.sub(r'\b' + termino_tecnico + r'\b', termino_humano, humanizada, flags=re.IGNORECASE)
        
        print(f"   ✅ Respuesta humanizada completada")
        return humanizada
        
    except Exception as e:
        print(f"   ⚠️  Error al humanizar respuesta: {e}")
        return respuesta_agente

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/ask', methods=['POST'])
def preguntar():
    try:
        datos = request.get_json()
        pregunta = datos.get('question', '').strip()
        
        print(f"\n{'='*60}")
        print(f"📥 Nueva pregunta recibida: '{pregunta}'")
        print(f"{'='*60}")
        
        if not pregunta:
            print("❌ Pregunta vacía recibida")
            return jsonify({'error': 'No se proporcionó ninguna pregunta'}), 400
        
        print("🔍 Verificando si hay dirección en la pregunta...")
        pregunta_con_coordenadas = detectar_y_convertir_direccion_en_pregunta(pregunta)
        if pregunta_con_coordenadas != pregunta:
            print("✅ Dirección detectada y convertida a coordenadas")
        else:
            print("ℹ️  No se detectó dirección, procediendo con la pregunta original")
        
        pregunta_mejorada = f"""
        Estás analizando datos de tráfico del Área Metropolitana de Guadalajara (AMG), México.
        
        Tienes acceso a una tabla llamada 'traffic_data' con estas columnas:
        - id (TEXT): identificador único de la ubicación (NO LO MENCIONES EN LA RESPUESTA, no es relevante para humanos)
        - predominant_color (TEXT): indicador de nivel de tráfico (ESTE ES EL CAMPO PRINCIPAL PARA DETERMINAR LA CALIDAD DEL TRÁFICO)
          * green = tráfico LIGERO/EXCELENTE (fluido, sin congestión) - MEJOR TRÁFICO
          * yellow = tráfico MEDIO (moderado, algo de congestión)
          * orange = tráfico MEDIO-ALTO (congestionado)
          * red = tráfico ALTO/PESADO (congestión severa, muy lento) - PEOR TRÁFICO
          * red_wine = tráfico MUY PESADO (congestión crítica, casi detenido) - EL PEOR TRÁFICO POSIBLE
          IMPORTANTE: Para identificar el MEJOR tráfico busca 'green'. Para el PEOR tráfico busca 'red_wine' y 'red'.
        - exponential_color_weighting (FLOAT): puntaje de congestión ponderado exponencial (mayor valor = peor tráfico)
        - linear_color_weighting (FLOAT): puntaje de congestión ponderado lineal (mayor valor = peor tráfico)
        - diffuse_logic_traffic (FLOAT): valor difuso (NO es relevante, ignóralo)
        - coordx (FLOAT): coordenada de LONGITUD (aproximadamente -103.2 a -103.5 para Guadalajara)
        - coordy (FLOAT): coordenada de LATITUD (aproximadamente 20.5 a 20.8 para Guadalajara)
        
        IMPORTANTE: 
        - Las coordenadas están en formato (longitud, latitud). Coordx es longitud (oeste de Greenwich, valores negativos) y Coordy es latitud.
        - Al buscar por coordenadas, usa una consulta de rango como: WHERE coordx BETWEEN (lon-0.01) AND (lon+0.01) AND coordy BETWEEN (lat-0.01) AND (lat+0.01)
        - SIEMPRE incluye las coordenadas (coordx y coordy) en tu respuesta cuando devuelvas datos de ubicaciones.
        - NO incluyas IDs en tu respuesta, no son útiles para humanos.
        
        LÍMITES DE CONSULTA (MUY IMPORTANTE):
        - SIEMPRE agrega "LIMIT 50" al final de TODAS tus consultas SQL
        - Si el usuario pregunta por una ubicación específica, limita a 20 resultados máximo
        - Si el usuario pregunta por un área amplia o condición general, limita a 50 resultados máximo
        - NUNCA devuelvas más de 60 filas bajo ninguna circunstancia
        - Si hay muchos resultados, prioriza los más relevantes (por ejemplo, los de mayor congestión) usando ORDER BY antes del LIMIT
        
        OPTIMIZACIÓN DE CONSULTAS (CRÍTICO - LEE ESTO PRIMERO):
        - SIEMPRE prefiere usar agregaciones (COUNT, AVG, MAX, MIN) en lugar de traer filas individuales
        - Usa GROUP BY cuando sea posible para resumir información en lugar de mostrar cada registro
        - Ejemplos de queries eficientes:
          * "¿Cuántos puntos con tráfico pesado?" -> SELECT COUNT(*) FROM traffic_data WHERE predominant_color IN ('red', 'red_wine')
          * "¿Dónde está el PEOR tráfico?" -> SELECT coordx, coordy FROM traffic_data WHERE predominant_color IN ('red_wine', 'red') ORDER BY CASE WHEN predominant_color='red_wine' THEN 1 ELSE 2 END LIMIT 20
          * "¿Dónde está el MEJOR tráfico?" -> SELECT coordx, coordy FROM traffic_data WHERE predominant_color = 'green' LIMIT 20
          * "¿Promedio de congestión en esta zona?" -> SELECT AVG(exponential_color_weighting), predominant_color FROM traffic_data WHERE ... GROUP BY predominant_color
          * "¿Distribución del tráfico?" -> SELECT predominant_color, COUNT(*) as cantidad FROM traffic_data GROUP BY predominant_color ORDER BY cantidad DESC
        - Solo trae filas individuales cuando el usuario pida ubicaciones específicas o "dónde está..."
        - Si el usuario pregunta "cómo está el tráfico en X", usa agregaciones para dar un resumen general, no listados completos
        - Entre traer 50 filas o hacer un GROUP BY que devuelva 3 filas, SIEMPRE elige el GROUP BY
        
        Pregunta del usuario: {pregunta_con_coordenadas}
        
        Por favor proporciona una respuesta clara y concisa en español. 
        OBLIGATORIO: Si mencionas ubicaciones, SIEMPRE incluye las coordenadas en formato "coordx: [valor], coordy: [valor]" para que puedan ser traducidas a nombres de calles.
        Cuando menciones niveles de tráfico, usa términos claros: 
        - tráfico ligero/excelente (green - MEJOR)
        - tráfico medio (yellow)
        - tráfico medio-alto (orange)
        - tráfico pesado/alto (red - PEOR)
        - tráfico muy pesado/crítico (red_wine - EL PEOR)
        Recuerda: Prefiere agregaciones y GROUP BY sobre listados completos. LIMIT 50 (o menos) en todas las consultas SQL.
        """
        
        print("🤖 Ejecutando agente SQL...")
        resultado = agent_executor.invoke({"input": pregunta_mejorada})
        print("✅ Ejecución del agente completada")
        
        respuesta = resultado.get('output', 'No se generó respuesta')
        print(f"📝 Respuesta sin procesar: {respuesta[:100]}..." if len(respuesta) > 100 else f"📝 Respuesta sin procesar: {respuesta}")
        
        # Post-procesar para humanizar la respuesta con nombres de zonas
        respuesta_humanizada = humanizar_respuesta_agente(respuesta)
        print(f"📝 Respuesta humanizada: {respuesta_humanizada[:100]}..." if len(respuesta_humanizada) > 100 else f"📝 Respuesta humanizada: {respuesta_humanizada}")
        
        print(f"✅ Solicitud procesada exitosamente")
        print(f"{'='*60}\n")
        return jsonify({
            'answer': respuesta_humanizada,
            'success': True
        })
        
    except Exception as e:
        print(f"\n❌ ERROR procesando pregunta: {e}")
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
