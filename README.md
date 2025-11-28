# Proyecto de Análisis de Tráfico AMG con LLM

Este proyecto implementa un asistente inteligente para consultar datos de tráfico del Área Metropolitana de Guadalajara (AMG) utilizando un agente LLM que puede interactuar con una base de datos Aurora PostgreSQL alojada en AWS.

## 👥 Equipo de Desarrollo

- **Sebastian Fernandez**
- **Ivan Cruz**

---

## 🏗️ Arquitectura del Proyecto

El proyecto utiliza la siguiente infraestructura en AWS:
- **Amazon Aurora PostgreSQL**: Base de datos con más de 3.9 millones de registros de tráfico
- **Amazon EC2**: Instancias para procesamiento de datos y servidor de aplicación
- **Amazon S3**: Almacenamiento de datos consolidados
- **OpenAI GPT-4**: Motor de lenguaje natural para el agente conversacional

## 📋 Proceso de Configuración

### 1. Configuración Inicial de AWS

La configuración del proyecto se realizó en varias fases utilizando los scripts disponibles en la carpeta `setup/`:

#### Fase 1: Procesamiento de Datos (Instancia EC2 t3.large)

Debido al gran volumen de datos a procesar, se utilizó una instancia **EC2 t3.large** para ejecutar los scripts de preparación de datos:

**Script: `load_traffic_data.py`**
- Clona los repositorios de datos de tráfico 2024 y 2025 de GitHub
- Procesa más de 5,852 archivos CSV históricos
- Combina los datos con información de ubicación geográfica
- Genera un archivo unificado con todos los registros
- Sube el archivo consolidado a S3

```bash
python load_traffic_data.py
```

Este proceso consolidó los datos de tráfico de 2024 y 2025 en un solo dataset.

**Script: `upload_s3_to_aurora.py`**
- Descarga el archivo consolidado desde S3
- Carga **3,985,212 registros** a Aurora PostgreSQL
- Utiliza el método COPY para inserción ultra rápida
- Crea la tabla `traffic_data` con las siguientes columnas:
  - `id`: Identificador del punto de medición
  - `predominant_color`: Color predominante del tráfico (green, yellow, orange, red)
  - `exponential_color_weighting`: Peso exponencial del color
  - `linear_color_weighting`: Peso lineal del color
  - `diffuse_logic_traffic`: Lógica difusa del tráfico
  - `coordx`: Longitud (coordenada X)
  - `coordy`: Latitud (coordenada Y)

```bash
python upload_s3_to_aurora.py
```

**Script de Verificación: `verify.py`**
- Verifica la conexión a Aurora
- Valida que los datos se hayan cargado correctamente
- Muestra estadísticas de los registros

### 2. Servidor de Aplicación (Instancia EC2 t3.micro)

Una vez procesados los datos, se cambió a una instancia **EC2 t3.micro** más económica para alojar el servidor de la aplicación, ya que esta requiere menos recursos computacionales.

## 🚀 Funcionamiento de la Aplicación

### Componente Principal: `AgentAPI/app.py`

La aplicación es un servidor Flask que integra varios componentes:

#### 1. **Agente SQL con LangChain**
- Utiliza `langchain` para crear un agente que puede generar y ejecutar consultas SQL
- El agente interpreta preguntas en lenguaje natural y las convierte en consultas a la base de datos
- Modelo: **GPT-4o-mini** de OpenAI

#### 2. **Geocodificación con Geopy**
- Convierte direcciones en coordenadas (y viceversa)
- Permite hacer consultas por nombre de calle o zona
- Enriquece los resultados con nombres de calles legibles

#### 3. **Funcionalidades Principales**

**Detección de direcciones:**
- El sistema detecta cuando el usuario menciona una dirección
- Convierte automáticamente la dirección a coordenadas
- Busca datos de tráfico en un radio de 0.01 grados alrededor de las coordenadas

**Humanización de respuestas:**
- Convierte coordenadas técnicas en nombres de calles
- Traduce IDs de puntos en ubicaciones comprensibles
- Presenta la información de forma amigable al usuario

**Interfaz Web:**
- Interfaz simple en HTML/CSS para interactuar con el agente
- Envía preguntas y recibe respuestas en tiempo real
- Ubicada en `AgentAPI/templates/index.html`

### Ejemplos de Consultas

El agente puede responder preguntas como:
- "¿Cuál es el tráfico en la Avenida López Mateos?"
- "¿Qué zonas tienen tráfico rojo en este momento?"
- "Muestra los puntos con mayor congestión cerca de Av. Américas"
- "¿Cuántos registros hay de tráfico verde?"

## 🔄 Ejecución del Servidor

Para ejecutar el servidor en la instancia EC2:

```bash
cd AgentAPI
python app.py
```

El servidor se inicia en el puerto por defecto de Flask (5000) y está listo para recibir consultas.

## 📊 Logs Disponibles

El proyecto incluye logs detallados del proceso de configuración y carga de datos:

### `setup/Logs.txt`
Contiene el output completo de los procesos de:
- Clonación de repositorios
- Procesamiento de 5,852 archivos CSV
- Unificación de datos
- Subida a S3
- Carga de 3,985,212 registros a Aurora
- Verificación de primeros registros

Estos logs son útiles para:
- Verificar que el proceso se completó correctamente
- Diagnosticar problemas en la carga de datos
- Confirmar el número de registros procesados
- Ver ejemplos de datos cargados

### `AgentAPI/Logs/`
Carpeta destinada a logs de la aplicación en tiempo de ejecución.

## 📦 Dependencias

### Setup (Procesamiento de Datos)
Ver `setup/requirements.txt` para las dependencias necesarias para el procesamiento inicial de datos.

### Aplicación Web
Ver `AgentAPI/requirements.txt` para las dependencias del servidor Flask y el agente LLM.

Principales dependencias:
- Flask: Servidor web
- LangChain: Framework para agentes LLM
- SQLAlchemy: ORM para base de datos
- OpenAI: API de GPT-4
- Geopy: Geocodificación

## 🔐 Configuración Requerida

Para ejecutar el proyecto, necesitas configurar:

1. **Credenciales de AWS**:
   - Acceso a S3
   - Acceso a Aurora PostgreSQL (host, usuario, contraseña)

2. **API Key de OpenAI**:
   - Requerida para el agente LLM
   - Debe configurarse en `app.py`

3. **Instancia EC2**:
   - Security groups configurados para permitir tráfico HTTP
   - Acceso SSH para despliegue

## 🎯 Casos de Uso

Este proyecto permite:
- Consultar datos históricos de tráfico en lenguaje natural
- Analizar patrones de congestión por zona
- Identificar puntos problemáticos de tráfico
- Obtener información de tráfico por dirección o coordenadas
- Generar insights sobre movilidad urbana en el AMG

---

**Desarrollado para análisis de tráfico vehicular en el Área Metropolitana de Guadalajara**
