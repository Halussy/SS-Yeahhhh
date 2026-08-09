from flask import Flask, render_template, request, session, redirect, url_for, jsonify, send_from_directory, send_file
from werkzeug.utils import secure_filename
from Estilos_Apren import EvaluadorEstilosAprendizaje
import sqlite3
from datetime import timedelta
import google.genai as genai
import os
import io
import random
import string
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

load_dotenv()

app = Flask(__name__)

_ESTILO_A_CLASE = {
    'Visual': 'visual',
    'Auditivo': 'auditivo',
    'Kinestésico': 'kinestesico',
    'Analítico': 'analitico',
}

@app.template_filter('estilo_clase')
def estilo_clase(nombre_estilo):
    """Mapea el nombre de un estilo de aprendizaje a su clase CSS (badge-<clase>).
    Filtro de plantilla puro: no lee ni escribe estado, no afecta ninguna ruta."""
    return _ESTILO_A_CLASE.get(nombre_estilo, 'visual')
app.secret_key = 'clave_secreta_servicio_social'
UPLOAD_FOLDER = 'uploads_tareas'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'png', 'jpg', 'jpeg', 'txt', 'zip'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS 
app.permanent_session_lifetime = timedelta(minutes=10)

api_key_secreta = os.getenv("GEMINI_API_KEY")
cliente_ia = genai.Client(api_key=api_key_secreta)

mi_evaluador = EvaluadorEstilosAprendizaje()

BASE_DE_DATOS = {
    "320001512": {
        "password": "123",
        "nombre": "Ricardo",
        "semestre": "8vo Semestre"
    },
    "423057353": {
        "password": "789",
        "nombre": "Armando Contreras Juarez",
        "semestre": "1er Semestre"
    }
}

PLAN_DE_ESTUDIOS = {
    "1er Semestre": [
        {"nombre": "Álgebra", "creditos": 10},
        {"nombre": "Cálculo Diferencial e Integral", "creditos": 8},
        {"nombre": "Geometría Analítica", "creditos": 8},
        {"nombre": "Simulación de Sistemas", "creditos": 8},
        {"nombre": "Algoritmos y Programación Estructurada", "creditos": 8},
        {"nombre": "Comunicación Oral y Escrita", "creditos": 6}
    ],
    "2do Semestre": [
        {"nombre": "Ética Profesional", "creditos": 6},
        {"nombre": "Cálculo Vectorial", "creditos": 10},
        {"nombre": "Estática", "creditos": 8},
        {"nombre": "Estructura de Datos", "creditos": 8},
        {"nombre": "Sistemas Operativos", "creditos": 8},
        {"nombre": "Transformadas Especiales", "creditos": 8},
        {"nombre": "Introducción al desarrollo sustentable", "creditos": 0}
    ],
    "3er Semestre": [
        {"nombre": "Electricidad y Magnetismo", "creditos": 10},
        {"nombre": "Cinemática y Dinámica", "creditos": 10},
        {"nombre": "Ingeniería de Software", "creditos": 8},
        {"nombre": "Neumática e Hidráulica", "creditos": 8},
        {"nombre": "Ecuaciones Diferenciales y en Diferencias", "creditos": 10},
        {"nombre": "Género, igualdad y cultura de paz", "creditos": 0}
    ],
    "4to Semestre": [
        {"nombre": "Fundamentos de Termodinámica", "creditos": 8},
        {"nombre": "Óptica y Acústica", "creditos": 10},
        {"nombre": "Comercialización en Tecnologías de Información", "creditos": 6},
        {"nombre": "Automatización y Electrónica", "creditos": 8},
        {"nombre": "Aspectos Básicos en el Desarrollo Empresarial", "creditos": 8},
        {"nombre": "Análisis de Sistemas y Señales", "creditos": 8},
        {"nombre": "Circuitos Eléctricos", "creditos": 10}
    ],
    "5to Semestre": [
        {"nombre": "Bases de Datos", "creditos": 8},
        {"nombre": "Probabilidad y Estadística", "creditos": 8},
        {"nombre": "Dispositivos y Circuitos Electrónicos", "creditos": 10},
        {"nombre": "Sistemas Digitales", "creditos": 10},
        {"nombre": "Teoría Electromagnética", "creditos": 10}
    ],
    "6to Semestre": [
        {"nombre": "Sistemas Analógicos", "creditos": 8},
        {"nombre": "Fundamentos de Sistemas de Comunicaciones", "creditos": 10},
        {"nombre": "Amplificación de Señales", "creditos": 10},
        {"nombre": "Ingeniería de Control", "creditos": 10},
        {"nombre": "Máquinas Eléctricas", "creditos": 10}
    ],
    "7mo Semestre": [
        {"nombre": "Sistemas de Datos Muestreados", "creditos": 8},
        {"nombre": "Microprocesadores", "creditos": 10},
        {"nombre": "Comunicaciones Digitales", "creditos": 10},
        {"nombre": "Electrónica Analógica", "creditos": 10},
        {"nombre": "Telefonía Digital", "creditos": 8}
    ],
    "8vo Semestre": [
        {"nombre": "Control Digital", "creditos": 10},
        {"nombre": "Microcontroladores", "creditos": 8},
        {"nombre": "Transmisión de Datos", "creditos": 8},
        {"nombre": "Dispositivos Lógicos Programables", "creditos": 8},
        {"nombre": "Sistemas de Audio y Video", "creditos": 8}
    ],
    "9no Semestre - Módulo: Comunicaciones": [
        {"nombre": "Sistemas de Comunicaciones Ópticos", "creditos": 8},
        {"nombre": "Antenas", "creditos": 8},
        {"nombre": "Microondas y Satélites", "creditos": 8}
    ],
    "9no Semestre - Módulo: Ingeniería de Control y Mecatrónica": [
        {"nombre": "Control Avanzado", "creditos": 8},
        {"nombre": "Autómatas Programables", "creditos": 8},
        {"nombre": "Robótica", "creditos": 8}
    ],
    "9no Semestre - Módulo: Sistemas Analógicos": [
        {"nombre": "Electrónica de Potencia", "creditos": 8},
        {"nombre": "Instrumentación Electrónica", "creditos": 8},
        {"nombre": "Sistemas Microelectrónicos Avanzados", "creditos": 8}
    ],
    "9no Semestre - Módulo: Sistemas de Información": [
        {"nombre": "Análisis de Redes de Datos", "creditos": 8},
        {"nombre": "Bases de Datos Avanzadas", "creditos": 8},
        {"nombre": "Desarrollo de Proyectos de Software", "creditos": 8}
    ],
    "9no Semestre - Módulo: Sistemas Digitales": [
        {"nombre": "Diseño de Sistemas Digitales", "creditos": 8},
        {"nombre": "Sistemas Basados en Redes Neuronales", "creditos": 8},
        {"nombre": "Sistemas Inteligentes", "creditos": 8}
    ],
    "Optativas de Elección": [
        {"nombre": "Control de Sistemas Difusos", "creditos": 8},
        {"nombre": "Bases de Datos Especiales", "creditos": 8},
        {"nombre": "Cableado Estructurado", "creditos": 8},
        {"nombre": "Compresión de Datos", "creditos": 8},
        {"nombre": "Control Adaptable", "creditos": 8},
        {"nombre": "Diseño de Sistemas de Comunicaciones", "creditos": 8},
        {"nombre": "Control de Sistemas No Lineales", "creditos": 8},
        {"nombre": "Control Difuso", "creditos": 8},
        {"nombre": "Control Estocástico", "creditos": 8},
        {"nombre": "Diseño de Interfaces de Usuario", "creditos": 8},
        {"nombre": "Dispositivos y Circuitos de Radiofrecuencia (RF)", "creditos": 8},
        {"nombre": "Diseño de Sistemas de Información", "creditos": 8},
        {"nombre": "Diseño de Sistemas Digitales Avanzados", "creditos": 8},
        {"nombre": "Dispositivos Electrónicos Especiales", "creditos": 8},
        {"nombre": "Dispositivos y Circuitos para Microondas", "creditos": 8},
        {"nombre": "Seguridad en Sistemas de Información", "creditos": 8},
        {"nombre": "Domótica", "creditos": 8},
        {"nombre": "Instrumentación Electrónica Avanzada", "creditos": 8},
        {"nombre": "Minería de Datos", "creditos": 8},
        {"nombre": "Procesamiento Digital de Señales", "creditos": 8},
        {"nombre": "Sistemas Expertos", "creditos": 8},
        {"nombre": "Sistemas Basados en Algoritmos Genéticos", "creditos": 8},
        {"nombre": "Sistemas de Automatización y Robótica", "creditos": 8},
        {"nombre": "Sistemas de Comunicación Inalámbricos Móviles", "creditos": 8},
        {"nombre": "Sistemas de Comunicaciones Multimedia", "creditos": 8},
        {"nombre": "Telemática", "creditos": 8},
        {"nombre": "Técnicas de Recuperación de Información", "creditos": 8},
        {"nombre": "Diseño de Aplicaciones para Dispositivos Móviles con Java", "creditos": 8}
    ]
}

# --- BASE DE DATOS ---
def get_db():
    conexion = sqlite3.connect('itse_fesc.db')
    conexion.row_factory = sqlite3.Row
    return conexion

def init_db():
    con = get_db()
    cur = con.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS alumnos
                    (cuenta TEXT PRIMARY KEY, password TEXT, nombre TEXT, semestre TEXT)''')
    cur.execute('''CREATE TABLE IF NOT EXISTS profesores
                    (usuario TEXT PRIMARY KEY, password TEXT, nombre TEXT)''')
    cur.execute('''CREATE TABLE IF NOT EXISTS administradores
                    (usuario TEXT PRIMARY KEY, password TEXT, nombre TEXT)''')
    cur.execute('''CREATE TABLE IF NOT EXISTS evaluaciones
                    (cuenta TEXT, materia TEXT, estilo TEXT, recomendacion TEXT,
                     PRIMARY KEY (cuenta, materia))''')
    cur.execute('''CREATE TABLE IF NOT EXISTS inscripciones
                    (cuenta TEXT, materia TEXT,
                     PRIMARY KEY (cuenta, materia))''')
    cur.execute('''CREATE TABLE IF NOT EXISTS correcciones_profesor
                    (cuenta TEXT, materia TEXT, recomendacion_corregida TEXT,
                     profesor TEXT, fecha TEXT,
                     PRIMARY KEY (cuenta, materia))''')

    # Migrar datos iniciales si las tablas están vacías
    if not cur.execute("SELECT 1 FROM alumnos LIMIT 1").fetchone():
        for cuenta, d in BASE_DE_DATOS.items():
            cur.execute("INSERT INTO alumnos VALUES (?,?,?,?)",
                        (cuenta, d["password"], d["nombre"], d["semestre"]))
    if not cur.execute("SELECT 1 FROM profesores LIMIT 1").fetchone():
        cur.execute("INSERT INTO profesores VALUES (?,?,?)", ("Profe01", "456", "Prof. García"))
    if not cur.execute("SELECT 1 FROM administradores LIMIT 1").fetchone():
        cur.execute("INSERT INTO administradores VALUES (?,?,?)", ("admin", "admin", "Administración FESC"))

    cur.execute('''CREATE TABLE IF NOT EXISTS actividades_ia
                    (id INTEGER PRIMARY KEY AUTOINCREMENT,
                     cuenta TEXT, materia TEXT, estilo TEXT,
                     actividad TEXT, actividad_corregida TEXT,
                     profesor_corrector TEXT, fecha_correccion TEXT)''')
    cur.execute('''CREATE TABLE IF NOT EXISTS tareas_profesor
                    (id INTEGER PRIMARY KEY AUTOINCREMENT,
                     cuenta TEXT, materia TEXT, titulo TEXT,
                     descripcion TEXT, fecha_entrega TEXT,
                     archivo TEXT, profesor TEXT, fecha_asignacion TEXT)''')
    cur.execute('''CREATE TABLE IF NOT EXISTS entregas_tarea
                    (id INTEGER PRIMARY KEY AUTOINCREMENT,
                     tarea_id INTEGER, cuenta TEXT,
                     archivo TEXT, comentario TEXT,
                     fecha_entrega TEXT,
                     calificacion TEXT, retroalimentacion TEXT,
                     fecha_calificacion TEXT,
                     FOREIGN KEY(tarea_id) REFERENCES tareas_profesor(id))''')
    con.commit()
    con.close()

init_db()

# --- HELPERS PARA LEER USUARIOS DESDE BD ---
def get_alumno(cuenta):
    con = get_db()
    row = con.execute("SELECT * FROM alumnos WHERE cuenta=?", (cuenta,)).fetchone()
    con.close()
    return dict(row) if row else None

def get_profesor(usuario):
    con = get_db()
    row = con.execute("SELECT * FROM profesores WHERE usuario=?", (usuario,)).fetchone()
    con.close()
    return dict(row) if row else None

def get_admin(usuario):
    con = get_db()
    row = con.execute("SELECT * FROM administradores WHERE usuario=?", (usuario,)).fetchone()
    con.close()
    return dict(row) if row else None

def get_todos_alumnos():
    con = get_db()
    rows = con.execute("SELECT * FROM alumnos").fetchall()
    con.close()
    return {r["cuenta"]: dict(r) for r in rows}

def get_todos_profesores():
    con = get_db()
    rows = con.execute("SELECT * FROM profesores").fetchall()
    con.close()
    return {r["usuario"]: dict(r) for r in rows}

def obtener_materias_inscritas(cuenta):
    conexion = sqlite3.connect('itse_fesc.db')
    cursor = conexion.cursor()
    cursor.execute("SELECT materia FROM inscripciones WHERE cuenta=? ", (cuenta,))
    filas = cursor.fetchall()
    conexion.close()
    return [fila[0] for fila in filas]

_CAPTCHA_CARACTERES = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_CAPTCHA_LONGITUD = 5
_CAPTCHA_ANCHO, _CAPTCHA_ALTO = 200, 70

def _generar_texto_captcha():
    return "".join(random.choices(_CAPTCHA_CARACTERES, k=_CAPTCHA_LONGITUD))

def _dibujar_captcha(texto):
    color_fondo = (random.randint(230, 245), random.randint(230, 245), random.randint(235, 248))
    imagen = Image.new('RGB', (_CAPTCHA_ANCHO, _CAPTCHA_ALTO), color=color_fondo)
    draw = ImageDraw.Draw(imagen)

    for _ in range(6):
        x1, y1 = random.randint(0, _CAPTCHA_ANCHO), random.randint(0, _CAPTCHA_ALTO)
        x2, y2 = random.randint(0, _CAPTCHA_ANCHO), random.randint(0, _CAPTCHA_ALTO)
        draw.line([(x1, y1), (x2, y2)], fill=(180, 190, 205), width=1)

    for _ in range(60):
        x, y = random.randint(0, _CAPTCHA_ANCHO), random.randint(0, _CAPTCHA_ALTO)
        draw.point((x, y), fill=(150, 160, 175))

    try:
        fuente = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 34)
    except (IOError, OSError):
        fuente = ImageFont.load_default()

    espaciado = _CAPTCHA_ANCHO // (_CAPTCHA_LONGITUD + 1)
    for i, letra in enumerate(texto):
        x = espaciado * (i + 1) - 10
        y = random.randint(12, 26)
        color_letra = (random.randint(11, 40), random.randint(42, 75), random.randint(74, 110))
        draw.text((x, y), letra, font=fuente, fill=color_letra)

    buffer = io.BytesIO()
    imagen.save(buffer, format='PNG')
    buffer.seek(0)
    return buffer

@app.route('/captcha')
def captcha():
    texto = _generar_texto_captcha()
    session['captcha'] = texto
    imagen_buffer = _dibujar_captcha(texto)
    response = send_file(imagen_buffer, mimetype='image/png')
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    return response

@app.route('/')
def raiz():
    if 'usuario' in session:
        return redirect(url_for('inicio'))
    if 'profesor' in session:
        return redirect(url_for('profesor_dashboard'))
    if 'admin' in session:
        return redirect(url_for('admin_dashboard'))
    return render_template('bienvenida.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        cuenta = request.form['numero_cuenta']
        password = request.form['password']
        
        captcha_input = request.form.get('captcha_input', '').strip().upper()
        captcha_correcto = session.get('captcha', '')
        if captcha_input != captcha_correcto:
            error = "El código CAPTCHA es incorrecto. Inténtalo de nuevo."
        else:
            alumno = get_alumno(cuenta)
            if alumno and alumno['password'] == password:
                session.permanent = True
                session['usuario'] = cuenta
                return redirect(url_for('inicio'))
            else:
                error = "Número de cuenta o contraseña incorrectos."
    return render_template('login.html', error=error)

@app.route('/inicio')
def inicio():
    if 'usuario' not in session: return redirect(url_for('login'))
    cuenta_actual = session['usuario']
    datos_alumno = get_alumno(cuenta_actual)
    datos_alumno['materias'] = obtener_materias_inscritas(cuenta_actual)

    conexion = sqlite3.connect('itse_fesc.db')
    cursor = conexion.cursor()
    cursor.execute("SELECT materia, estilo, recomendacion FROM evaluaciones WHERE cuenta=?", (cuenta_actual,))
    filas = cursor.fetchall()
    conexion.close()
    tips_ia = [{"materia": f[0], "estilo": f[1], "consejo": f[2]} for f in filas]
    return render_template('inicio.html', alumno=datos_alumno, tips_ia=tips_ia)

@app.route('/materias')
def materias():
    if 'usuario' not in session: return redirect(url_for('login'))
    cuenta_actual = session['usuario']
    datos_alumno = get_alumno(cuenta_actual)
    datos_alumno['materias'] = obtener_materias_inscritas(cuenta_actual)
    return render_template('materias.html', alumno=datos_alumno, plan=PLAN_DE_ESTUDIOS)

@app.route('/guardar_materias', methods=['POST'])
def guardar_materias():
    if 'usuario' not in session: return redirect(url_for('login'))
    
    cuenta_actual = session['usuario']
    materias_seleccionadas = request.form.getlist('materias_inscritas')
    
    total_creditos = 0
    for semestre, lista in PLAN_DE_ESTUDIOS.items():
        for mat in lista:
            if mat['nombre'] in materias_seleccionadas:
                total_creditos += mat['creditos']
                
    if total_creditos <= 64:
        conexion = sqlite3.connect('itse_fesc.db')
        cursor = conexion.cursor()
        cursor.execute("DELETE FROM inscripciones WHERE cuenta=?", (cuenta_actual,))
        for mat in materias_seleccionadas:
            cursor.execute("INSERT INTO inscripciones (cuenta, materia) VALUES (?, ?)", (cuenta_actual, mat))
        conexion.commit()
        conexion.close()
        
    return redirect(url_for('mis_materias'))

@app.route('/mis_materias')
def mis_materias():
    if 'usuario' not in session: return redirect(url_for('login'))
    cuenta_actual = session['usuario']
    datos_alumno = get_alumno(cuenta_actual)
    datos_alumno['materias'] = obtener_materias_inscritas(cuenta_actual)

    conexion = sqlite3.connect('itse_fesc.db')
    cursor = conexion.cursor()
    cursor.execute("SELECT materia, estilo FROM evaluaciones WHERE cuenta=?", (cuenta_actual,))
    filas = cursor.fetchall()
    conexion.close()
    resultados_guardados = {fila[0]: fila[1] for fila in filas}
    return render_template('mis_materias.html', alumno=datos_alumno, resultados=resultados_guardados)

@app.route('/logout')
def logout():
    session.pop('usuario', None)
    return redirect(url_for('login'))

@app.route('/test/<nombre_materia>')
def test_materia(nombre_materia):
    if 'usuario' not in session: return redirect(url_for('login'))
    return render_template('index.html', lista_preguntas=mi_evaluador.preguntas, materia=nombre_materia)

@app.route('/evaluar', methods=['POST'])
def evaluar():
    if 'usuario' not in session: return redirect(url_for('login'))
    if request.method == 'POST':
        materia_evaluada = request.form.get('materia_oculta')
        respuestas_usuario = [request.form.get(f'p{i}') for i in range(len(mi_evaluador.preguntas))]
        resultados = mi_evaluador.evaluar_desde_web(respuestas_usuario)
        estilo_ganador = resultados['estilo_ganador']['nombre']
        cuenta_actual = session['usuario']
        
        prompt = f"Actúa como un profesor de la FES Cuautitlán. Para un alumno que aprende de forma {estilo_ganador} en la materia '{materia_evaluada}', escribe estrictamente 3 cosas separadas por un salto de línea:\n1. Consejo: Un tip rápido.\n2. Libro: Un libro.\n3. Recurso: Un canal de YouTube.\nPor favor, NO uses asteriscos."
        try:
            respuesta_ia = cliente_ia.models.generate_content(model='gemini-2.5-flash', contents=prompt)
            consejo_generado = respuesta_ia.text
        except Exception:
            consejo_generado = "1. Consejo: Haz mapas mentales.\n2. Libro: Consulta la bibliografía oficial.\n3. Recurso: Busca tutoriales en YouTube."
        
        # Generar actividades IA
        prompt_actividades = f"Actúa como un profesor de la FES Cuautitlán. Para un alumno con estilo de aprendizaje {estilo_ganador} en la materia '{materia_evaluada}', genera exactamente 3 actividades de estudio prácticas y concretas. Escríbelas numeradas (1. 2. 3.) separadas por salto de línea. Cada actividad debe tener un título corto seguido de dos puntos y una descripción breve. NO uses asteriscos."
        try:
            resp_act = cliente_ia.models.generate_content(model='gemini-2.5-flash', contents=prompt_actividades)
            actividades_generadas = resp_act.text
        except Exception:
            actividades_generadas = "1. Mapas conceptuales: Organiza los temas en esquemas visuales.\n2. Fichas de repaso: Resume cada tema en tarjetas de estudio.\n3. Práctica guiada: Resuelve ejercicios del libro paso a paso."

        conexion = sqlite3.connect('itse_fesc.db')
        cursor = conexion.cursor()
        cursor.execute("REPLACE INTO evaluaciones (cuenta, materia, estilo, recomendacion) VALUES (?, ?, ?, ?)",
                       (cuenta_actual, materia_evaluada, estilo_ganador, consejo_generado))
        # Guardar actividades IA (reemplazar si ya existe)
        cursor.execute("DELETE FROM actividades_ia WHERE cuenta=? AND materia=?", (cuenta_actual, materia_evaluada))
        cursor.execute("INSERT INTO actividades_ia (cuenta, materia, estilo, actividad) VALUES (?,?,?,?)",
                       (cuenta_actual, materia_evaluada, estilo_ganador, actividades_generadas))
        conexion.commit()
        conexion.close()
        return render_template('resultado.html', datos=resultados, materia=materia_evaluada)

# --- RUTAS DE LA MASCOTA ---
@app.route('/chat_soporte', methods=['POST'])
def chat_soporte():
    if 'usuario' not in session:
        return jsonify({"response": "Por favor, inicia sesión primero."}), 403

    data = request.get_json()
    mensaje_usuario = data.get('message')

    if not mensaje_usuario:
        return jsonify({"response": "No recibí ningún mensaje."}), 400

    prompt_mascota = f"""
    Actúa como la mascota oficial y amigable de apoyo para estudiantes de Ingeniería ITSE en la FES Cuautitlán. 
    Tu objetivo es resolver dudas cortas sobre estilos de aprendizaje, dar ánimos para estudiar, o guiar sobre cómo usar este portal.
    Responde de forma concisa (máximo 3 oraciones), motivadora y usa un tono cercano.
    Si te preguntan algo no relacionado con la escuela o el estudio, declina amablemente responder y enfoca la plática al estudio.

    Pregunta del estudiante: '{mensaje_usuario}'
    """

    try:
        respuesta_ia = cliente_ia.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt_mascota
        )
        respuesta_final = respuesta_ia.text
    except Exception as e:
        print(f"Error en Chatbot: {e}")
        respuesta_final = "¡Hola! Ahorita ando un poco distraído, ¿me repites la pregunta en un momento?"

    return jsonify({"response": respuesta_final})



# --- TAREAS Y ACTIVIDADES ---

@app.route('/mis_actividades')
def mis_actividades():
    if 'usuario' not in session: return redirect(url_for('login'))
    cuenta_actual = session['usuario']
    datos_alumno = get_alumno(cuenta_actual)
    datos_alumno['materias'] = obtener_materias_inscritas(cuenta_actual)

    con = get_db()
    actividades = con.execute(
        "SELECT materia, estilo, actividad, actividad_corregida FROM actividades_ia WHERE cuenta=? ORDER BY materia",
        (cuenta_actual,)).fetchall()
    tareas = con.execute(
        "SELECT id, materia, titulo, descripcion, fecha_entrega, archivo, profesor, fecha_asignacion FROM tareas_profesor WHERE cuenta=? ORDER BY fecha_entrega",
        (cuenta_actual,)).fetchall()
    # Obtener entregas del alumno
    entregas = {row['tarea_id']: dict(row) for row in con.execute(
        "SELECT * FROM entregas_tarea WHERE cuenta=?", (cuenta_actual,)).fetchall()}
    con.close()

    return render_template('mis_actividades.html',
                           alumno=datos_alumno,
                           actividades=[dict(a) for a in actividades],
                           tareas=[dict(t) for t in tareas],
                           entregas=entregas)

@app.route('/uploads_tareas/<filename>')
def descargar_archivo(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# --- RUTAS PROFESOR: TAREAS Y CORRECCIÓN DE ACTIVIDADES ---

@app.route('/profesor/tareas')
def profesor_tareas():
    if 'profesor' not in session: return redirect(url_for('profesor_login'))
    nombre_profesor = get_profesor(session['profesor'])['nombre']

    con = get_db()
    # Todos los alumnos con evaluaciones
    alumnos_eval = con.execute(
        "SELECT DISTINCT cuenta FROM actividades_ia ORDER BY cuenta").fetchall()
    actividades = {}
    for row in alumnos_eval:
        cuenta = row['cuenta']
        alumno = get_alumno(cuenta)
        nombre = alumno['nombre'] if alumno else cuenta
        acts = con.execute(
            "SELECT id, materia, estilo, actividad, actividad_corregida, profesor_corrector FROM actividades_ia WHERE cuenta=?",
            (cuenta,)).fetchall()
        actividades[cuenta] = {'nombre': nombre, 'cuenta': cuenta, 'actividades': [dict(a) for a in acts]}

    # Tareas ya asignadas por este profesor
    tareas = con.execute(
        "SELECT t.*, a.nombre as nombre_alumno FROM tareas_profesor t LEFT JOIN alumnos a ON t.cuenta=a.cuenta WHERE t.profesor=? ORDER BY t.fecha_asignacion DESC",
        (nombre_profesor,)).fetchall()

    todos_alumnos = con.execute("SELECT cuenta, nombre FROM alumnos ORDER BY nombre").fetchall()
    materias_disponibles = con.execute("SELECT DISTINCT materia FROM evaluaciones ORDER BY materia").fetchall()

    # Entregas de cada tarea
    entregas_por_tarea = {}
    for t in tareas:
        ents = con.execute(
            """SELECT e.*, a.nombre as nombre_alumno FROM entregas_tarea e
               LEFT JOIN alumnos a ON e.cuenta=a.cuenta
               WHERE e.tarea_id=?""", (t['id'],)).fetchall()
        entregas_por_tarea[t['id']] = [dict(e) for e in ents]
    con.close()

    return render_template('profesor_tareas.html',
                           profesor=nombre_profesor,
                           actividades=actividades.values(),
                           tareas=[dict(t) for t in tareas],
                           todos_alumnos=[dict(a) for a in todos_alumnos],
                           materias=[m['materia'] for m in materias_disponibles],
                           entregas_por_tarea=entregas_por_tarea)

@app.route('/profesor/corregir_actividad', methods=['POST'])
def profesor_corregir_actividad():
    if 'profesor' not in session: return redirect(url_for('profesor_login'))
    from datetime import datetime
    act_id     = request.form['actividad_id']
    corregida  = request.form['actividad_corregida']
    nombre_prof = get_profesor(session['profesor'])['nombre']
    fecha       = datetime.now().strftime('%d/%m/%Y %H:%M')

    con = get_db()
    con.execute("UPDATE actividades_ia SET actividad_corregida=?, profesor_corrector=?, fecha_correccion=? WHERE id=?",
                (corregida, nombre_prof, fecha, act_id))
    con.commit()
    con.close()
    return redirect(url_for('profesor_tareas'))

@app.route('/profesor/asignar_tarea', methods=['POST'])
def profesor_asignar_tarea():
    if 'profesor' not in session: return redirect(url_for('profesor_login'))
    from datetime import datetime
    cuenta        = request.form['cuenta']
    materia       = request.form['materia']
    titulo        = request.form['titulo']
    descripcion   = request.form['descripcion']
    fecha_entrega = request.form['fecha_entrega']
    nombre_prof   = get_profesor(session['profesor'])['nombre']
    fecha_hoy     = datetime.now().strftime('%d/%m/%Y %H:%M')

    archivo_nombre = None
    if 'archivo' in request.files:
        archivo = request.files['archivo']
        if archivo and archivo.filename and allowed_file(archivo.filename):
            filename = secure_filename(archivo.filename)
            archivo.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            archivo_nombre = filename

    con = get_db()
    con.execute("INSERT INTO tareas_profesor (cuenta, materia, titulo, descripcion, fecha_entrega, archivo, profesor, fecha_asignacion) VALUES (?,?,?,?,?,?,?,?)",
                (cuenta, materia, titulo, descripcion, fecha_entrega, archivo_nombre, nombre_prof, fecha_hoy))
    con.commit()
    con.close()
    return redirect(url_for('profesor_tareas'))

# --- RUTAS DEL PROFESOR ---

@app.route("/profesor/login", methods=["GET", "POST"])
def profesor_login():
    error = None
    if request.method == "POST":
        usuario = request.form["usuario"]
        password = request.form["password"]
        captcha_input = request.form.get('captcha_input', '').strip().upper()
        captcha_correcto = session.get('captcha', '')
        if captcha_input != captcha_correcto:
            error = "El código CAPTCHA es incorrecto. Inténtalo de nuevo."
        else:
            prof = get_profesor(usuario)
            if prof and prof["password"] == password:
                session.permanent = True
                session["profesor"] = usuario
                return redirect(url_for("profesor_dashboard"))
            else:
                error = "Usuario o contraseña incorrectos."
    return render_template("profesor_login.html", error=error)

@app.route("/profesor/logout")
def profesor_logout():
    session.pop("profesor", None)
    return redirect(url_for("profesor_login"))

@app.route("/profesor/dashboard")
def profesor_dashboard():
    if "profesor" not in session:
        return redirect(url_for("profesor_login"))
    nombre_profesor = get_profesor(session["profesor"])["nombre"]

    conexion = sqlite3.connect("itse_fesc.db")
    cursor = conexion.cursor()
    cursor.execute("""
        SELECT e.cuenta, e.materia, e.estilo, e.recomendacion,
               c.recomendacion_corregida, c.profesor, c.fecha
        FROM evaluaciones e
        LEFT JOIN correcciones_profesor c
            ON e.cuenta = c.cuenta AND e.materia = c.materia
        ORDER BY e.cuenta, e.materia
    """)
    filas = cursor.fetchall()
    conexion.close()

    alumnos = {}
    for fila in filas:
        cuenta, materia, estilo, rec_ia, rec_corregida, prof_corrector, fecha = fila
        alumno_row = get_alumno(cuenta)
        nombre_alumno = alumno_row["nombre"] if alumno_row else cuenta
        if cuenta not in alumnos:
            alumnos[cuenta] = {"nombre": nombre_alumno, "cuenta": cuenta, "evaluaciones": []}
        alumnos[cuenta]["evaluaciones"].append({
            "materia": materia,
            "estilo": estilo,
            "recomendacion_ia": rec_ia,
            "recomendacion_corregida": rec_corregida,
            "profesor_corrector": prof_corrector,
            "fecha_correccion": fecha
        })

    return render_template("profesor_dashboard.html",
                           profesor=nombre_profesor,
                           alumnos=alumnos.values())

@app.route("/profesor/corregir", methods=["POST"])
def profesor_corregir():
    if "profesor" not in session:
        return redirect(url_for("profesor_login"))

    from datetime import datetime
    cuenta = request.form["cuenta"]
    materia = request.form["materia"]
    nueva_recomendacion = request.form["nueva_recomendacion"]
    usuario_profesor = session["profesor"]
    nombre_profesor = get_profesor(usuario_profesor)["nombre"]
    fecha_hoy = datetime.now().strftime("%d/%m/%Y %H:%M")

    conexion = sqlite3.connect("itse_fesc.db")
    cursor = conexion.cursor()
    cursor.execute("""REPLACE INTO correcciones_profesor
                      (cuenta, materia, recomendacion_corregida, profesor, fecha)
                      VALUES (?, ?, ?, ?, ?)""",
                   (cuenta, materia, nueva_recomendacion, nombre_profesor, fecha_hoy))
    conexion.commit()
    conexion.close()

    return redirect(url_for("profesor_dashboard"))


# --- ADMINISTRATIVO ---

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = None
    if request.method == "POST":
        usuario = request.form["usuario"]
        password = request.form["password"]
        adm = get_admin(usuario)
        if adm and adm["password"] == password:
            session.permanent = True
            session["admin"] = usuario
            return redirect(url_for("admin_dashboard"))
        else:
            error = "Usuario o contraseña incorrectos."
    return render_template("admin_login.html", error=error)

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("admin_login"))

@app.route("/admin/dashboard")
def admin_dashboard():
    if "admin" not in session:
        return redirect(url_for("admin_login"))
    nombre_admin = get_admin(session["admin"])["nombre"]

    conexion = sqlite3.connect("itse_fesc.db")
    cursor = conexion.cursor()

    # Estadísticas generales
    cursor.execute("SELECT COUNT(DISTINCT cuenta) FROM evaluaciones")
    total_alumnos_evaluados = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM evaluaciones")
    total_evaluaciones = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM correcciones_profesor")
    total_correcciones = cursor.fetchone()[0]

    cursor.execute("SELECT estilo, COUNT(*) as cnt FROM evaluaciones GROUP BY estilo ORDER BY cnt DESC")
    estilos_stats = cursor.fetchall()

    # Detalle de alumnos
    cursor.execute("""
        SELECT e.cuenta, e.materia, e.estilo, e.recomendacion,
               c.recomendacion_corregida, c.profesor, c.fecha
        FROM evaluaciones e
        LEFT JOIN correcciones_profesor c
            ON e.cuenta = c.cuenta AND e.materia = c.materia
        ORDER BY e.cuenta, e.materia
    """)
    filas = cursor.fetchall()
    conexion.close()

    alumnos = {}
    for fila in filas:
        cuenta, materia, estilo, rec_ia, rec_corregida, prof_corrector, fecha = fila
        alumno_row = get_alumno(cuenta)
        nombre_alumno = alumno_row["nombre"] if alumno_row else cuenta
        semestre = alumno_row["semestre"] if alumno_row else "—"
        if cuenta not in alumnos:
            alumnos[cuenta] = {"nombre": nombre_alumno, "cuenta": cuenta, "semestre": semestre, "evaluaciones": []}
        alumnos[cuenta]["evaluaciones"].append({
            "materia": materia,
            "estilo": estilo,
            "recomendacion_ia": rec_ia,
            "recomendacion_corregida": rec_corregida,
            "profesor_corrector": prof_corrector,
            "fecha_correccion": fecha
        })

    todos_alumnos = get_todos_alumnos()
    todos_profesores = get_todos_profesores()
    con = get_db()
    todos_admins = {r["usuario"]: dict(r) for r in con.execute("SELECT * FROM administradores").fetchall()}
    con.close()
    return render_template("admin_dashboard.html",
                           admin=nombre_admin,
                           admin_activo=session["admin"],
                           alumnos=alumnos.values(),
                           total_alumnos=len(todos_alumnos),
                           total_profesores=len(todos_profesores),
                           total_alumnos_evaluados=total_alumnos_evaluados,
                           total_evaluaciones=total_evaluaciones,
                           total_correcciones=total_correcciones,
                           estilos_stats=estilos_stats,
                           profesores=todos_profesores,
                           base_alumnos=todos_alumnos,
                           admins=todos_admins)

@app.route("/admin/agregar_alumno", methods=["POST"])
def admin_agregar_alumno():
    if "admin" not in session:
        return redirect(url_for("admin_login"))
    cuenta = request.form["cuenta"].strip()
    nombre = request.form["nombre"].strip()
    password = request.form["password"].strip()
    semestre = request.form["semestre"].strip()
    if cuenta and nombre and password and semestre:
        con = get_db()
        con.execute("INSERT OR REPLACE INTO alumnos VALUES (?,?,?,?)", (cuenta, password, nombre, semestre))
        con.commit()
        con.close()
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/agregar_profesor", methods=["POST"])
def admin_agregar_profesor():
    if "admin" not in session:
        return redirect(url_for("admin_login"))
    usuario = request.form["usuario"].strip()
    nombre = request.form["nombre"].strip()
    password = request.form["password"].strip()
    if usuario and nombre and password:
        con = get_db()
        con.execute("INSERT OR REPLACE INTO profesores VALUES (?,?,?)", (usuario, password, nombre))
        con.commit()
        con.close()
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/eliminar_alumno", methods=["POST"])
def admin_eliminar_alumno():
    if "admin" not in session:
        return redirect(url_for("admin_login"))
    cuenta = request.form["cuenta"].strip()
    if cuenta:
        con = get_db()
        con.execute("DELETE FROM alumnos WHERE cuenta=?", (cuenta,))
        con.execute("DELETE FROM inscripciones WHERE cuenta=?", (cuenta,))
        con.execute("DELETE FROM evaluaciones WHERE cuenta=?", (cuenta,))
        con.execute("DELETE FROM actividades_ia WHERE cuenta=?", (cuenta,))
        con.execute("DELETE FROM tareas_profesor WHERE cuenta=?", (cuenta,))
        con.commit()
        con.close()
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/eliminar_profesor", methods=["POST"])
def admin_eliminar_profesor():
    if "admin" not in session:
        return redirect(url_for("admin_login"))
    usuario = request.form["usuario"].strip()
    if usuario:
        con = get_db()
        con.execute("DELETE FROM profesores WHERE usuario=?", (usuario,))
        con.commit()
        con.close()
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/agregar_admin", methods=["POST"])
def admin_agregar_admin():
    if "admin" not in session:
        return redirect(url_for("admin_login"))
    usuario = request.form["usuario"].strip()
    nombre  = request.form["nombre"].strip()
    password = request.form["password"].strip()
    if usuario and nombre and password:
        con = get_db()
        con.execute("INSERT OR REPLACE INTO administradores VALUES (?,?,?)", (usuario, password, nombre))
        con.commit()
        con.close()
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/eliminar_admin", methods=["POST"])
def admin_eliminar_admin():
    if "admin" not in session:
        return redirect(url_for("admin_login"))
    usuario = request.form["usuario"].strip()
    # No permitir eliminar al admin activo
    if usuario and usuario != session["admin"]:
        con = get_db()
        con.execute("DELETE FROM administradores WHERE usuario=?", (usuario,))
        con.commit()
        con.close()
    return redirect(url_for("admin_dashboard"))


# --- ENTREGAS DE TAREAS ---

@app.route('/entregar_tarea/<int:tarea_id>', methods=['POST'])
def entregar_tarea(tarea_id):
    if 'usuario' not in session:
        return redirect(url_for('login'))
    from datetime import datetime
    cuenta = session['usuario']
    comentario = request.form.get('comentario', '').strip()
    fecha = datetime.now().strftime('%d/%m/%Y %H:%M')

    archivo_nombre = None
    if 'archivo_entrega' in request.files:
        archivo = request.files['archivo_entrega']
        if archivo and archivo.filename and allowed_file(archivo.filename):
            filename = secure_filename(f"entrega_{cuenta}_{tarea_id}_{archivo.filename}")
            archivo.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            archivo_nombre = filename

    con = get_db()
    # Reemplazar entrega anterior si ya existía
    con.execute("DELETE FROM entregas_tarea WHERE tarea_id=? AND cuenta=?", (tarea_id, cuenta))
    con.execute("""INSERT INTO entregas_tarea (tarea_id, cuenta, archivo, comentario, fecha_entrega)
                   VALUES (?,?,?,?,?)""", (tarea_id, cuenta, archivo_nombre, comentario, fecha))
    con.commit()
    con.close()
    return redirect(url_for('mis_actividades'))

@app.route('/profesor/calificar_entrega', methods=['POST'])
def profesor_calificar_entrega():
    if 'profesor' not in session:
        return redirect(url_for('profesor_login'))
    from datetime import datetime
    entrega_id      = request.form['entrega_id']
    calificacion    = request.form['calificacion']
    retroalimentacion = request.form['retroalimentacion']
    fecha = datetime.now().strftime('%d/%m/%Y %H:%M')

    con = get_db()
    con.execute("""UPDATE entregas_tarea
                   SET calificacion=?, retroalimentacion=?, fecha_calificacion=?
                   WHERE id=?""", (calificacion, retroalimentacion, fecha, entrega_id))
    con.commit()
    con.close()
    return redirect(url_for('profesor_tareas'))


# --- REPORTE PDF ADMINISTRATIVO ---

@app.route("/admin/reporte")
def admin_reporte():
    if "admin" not in session:
        return redirect(url_for("admin_login"))

    import io, matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                    TableStyle, HRFlowable, PageBreak,
                                    Image as RLImage, KeepTogether)
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from datetime import datetime

    # ── Paleta ────────────────────────────────────────────────────────────
    AZUL   = '#002B5C'
    DORADO = '#D4A12A'
    VERDE  = '#27ae60'
    ROJO   = '#e74c3c'
    GRIS   = '#f5f6fa'
    GRIS2  = '#e8edf2'
    PALETA = ['#002B5C','#D4A12A','#27ae60','#e74c3c','#8e44ad','#16a085']

    def rl(h): return colors.HexColor(h)

    # ── Datos ─────────────────────────────────────────────────────────────
    con = get_db()
    alumnos_db    = con.execute("SELECT * FROM alumnos ORDER BY nombre").fetchall()
    profesores_db = con.execute("SELECT * FROM profesores ORDER BY nombre").fetchall()
    evaluaciones  = con.execute("""
        SELECT e.cuenta, e.materia, e.estilo,
               c.recomendacion_corregida, c.profesor, c.fecha
        FROM evaluaciones e
        LEFT JOIN correcciones_profesor c
               ON e.cuenta=c.cuenta AND e.materia=c.materia
        ORDER BY e.cuenta, e.materia""").fetchall()
    tareas_db = con.execute("""
        SELECT t.*, a.nombre as nombre_alumno, COUNT(en.id) as total_entregas
        FROM tareas_profesor t
        LEFT JOIN alumnos a ON t.cuenta=a.cuenta
        LEFT JOIN entregas_tarea en ON t.id=en.tarea_id
        GROUP BY t.id ORDER BY t.fecha_asignacion DESC""").fetchall()
    estilos_raw = con.execute(
        "SELECT estilo, COUNT(*) as c FROM evaluaciones GROUP BY estilo ORDER BY c DESC"
    ).fetchall()
    materias_raw = con.execute(
        "SELECT materia, COUNT(*) as c FROM evaluaciones GROUP BY materia ORDER BY c DESC LIMIT 8"
    ).fetchall()
    semestres_raw = con.execute(
        "SELECT semestre, COUNT(*) as c FROM alumnos WHERE semestre IS NOT NULL GROUP BY semestre ORDER BY semestre"
    ).fetchall()
    total_corr  = con.execute("SELECT COUNT(*) FROM correcciones_profesor").fetchone()[0]
    total_entr  = con.execute("SELECT COUNT(*) FROM entregas_tarea").fetchone()[0]
    corr_estilo = {}
    for est, _ in estilos_raw:
        c = con.execute("""SELECT COUNT(*) FROM correcciones_profesor c2
            JOIN evaluaciones e2 ON c2.cuenta=e2.cuenta AND c2.materia=e2.materia
            WHERE e2.estilo=?""", (est,)).fetchone()[0]
        corr_estilo[est] = c
    con.close()

    eval_por_cuenta = {}
    for e in evaluaciones:
        eval_por_cuenta.setdefault(e["cuenta"], []).append(e["materia"])
    fecha_reporte = datetime.now().strftime('%d/%m/%Y %H:%M')

    # ── Helper fig→RL ─────────────────────────────────────────────────────
    def fig2rl(fig, w, h):
        buf = io.BytesIO()
        fig.savefig(buf, format='PNG', dpi=160, bbox_inches='tight',
                    facecolor='white', edgecolor='none')
        plt.close(fig)
        buf.seek(0)
        return RLImage(buf, width=w*inch, height=h*inch)

    # ── Gráfica A: Pastel estilos ─────────────────────────────────────────
    def g_pastel():
        if not estilos_raw: return None
        labs = [r[0].capitalize() for r in estilos_raw]
        vals = [r[1] for r in estilos_raw]
        fig, ax = plt.subplots(figsize=(3.6, 2.8))
        wedges, texts, autos = ax.pie(
            vals, labels=labs, colors=PALETA[:len(vals)],
            autopct=lambda p: f'{p:.0f}%', startangle=140,
            pctdistance=0.72,
            wedgeprops=dict(edgecolor='white', linewidth=1.5))
        for a in autos:
            a.set_fontsize(7.5); a.set_color('white'); a.set_fontweight('bold')
        for t in texts:
            t.set_fontsize(7.5)
        ax.set_title('Estilos de Aprendizaje', fontsize=9,
                     fontweight='bold', color=AZUL, pad=8)
        fig.tight_layout(pad=0.3)
        return fig2rl(fig, 3.2, 2.6)

    # ── Gráfica B: Barras agrupadas estilos vs correcciones ───────────────
    def g_barras_estilos():
        if not estilos_raw: return None
        ests  = [r[0].capitalize() for r in estilos_raw]
        tots  = [r[1] for r in estilos_raw]
        corrs = [corr_estilo.get(r[0], 0) for r in estilos_raw]
        x = np.arange(len(ests))
        fig, ax = plt.subplots(figsize=(3.6, 2.8))
        b1 = ax.bar(x-0.18, tots,  0.32, label='Evaluaciones', color=AZUL,   edgecolor='white')
        b2 = ax.bar(x+0.18, corrs, 0.32, label='Corregidas',   color=DORADO, edgecolor='white')
        ax.set_xticks(x); ax.set_xticklabels(ests, fontsize=7.5, rotation=12)
        ax.set_title('Evaluaciones vs Correcciones', fontsize=9,
                     fontweight='bold', color=AZUL, pad=8)
        ax.yaxis.set_major_locator(plt.MaxNLocator(integer=True))
        ax.legend(fontsize=7, framealpha=0.7, loc='upper right')
        ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)
        ax.tick_params(labelsize=7.5)
        for bar in list(b1)+list(b2):
            h = bar.get_height()
            if h > 0:
                ax.text(bar.get_x()+bar.get_width()/2, h+0.05,
                        str(int(h)), ha='center', va='bottom', fontsize=7, fontweight='bold')
        fig.tight_layout(pad=0.3)
        return fig2rl(fig, 3.2, 2.6)

    # ── Gráfica C: Barras horizontales materias ───────────────────────────
    def g_materias():
        if not materias_raw: return None
        noms = [r[0] if len(r[0])<=24 else r[0][:22]+'…' for r in materias_raw]
        vals = [r[1] for r in materias_raw]
        h_in = max(2.2, len(noms)*0.38)
        fig, ax = plt.subplots(figsize=(3.4, h_in))
        bars = ax.barh(noms, vals,
                       color=[PALETA[i%len(PALETA)] for i in range(len(vals))],
                       edgecolor='white', height=0.55)
        ax.set_xlabel('Evaluaciones', fontsize=7, color='#555')
        ax.set_title('Materias Evaluadas', fontsize=9,
                     fontweight='bold', color=AZUL, pad=8)
        ax.xaxis.set_major_locator(plt.MaxNLocator(integer=True))
        ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)
        ax.tick_params(axis='y', labelsize=7); ax.tick_params(axis='x', labelsize=7)
        for bar, val in zip(bars, vals):
            ax.text(bar.get_width()+0.03, bar.get_y()+bar.get_height()/2,
                    str(val), va='center', ha='left', fontsize=7, fontweight='bold')
        ax.set_xlim(0, max(vals)*1.3)
        fig.tight_layout(pad=0.3)
        return fig2rl(fig, 3.2, h_in)

    # ── Gráfica D: Dona tareas ────────────────────────────────────────────
    def g_dona():
        total_t = len(tareas_db)
        if total_t == 0: return None
        con_ent = min(total_entr, total_t)
        sin_ent = max(0, total_t - con_ent)
        vals = [con_ent, sin_ent] if (con_ent+sin_ent)>0 else [1,0]
        labs = ['Con entregas', 'Sin entregas']
        cols = [VERDE, '#d0d0d0']
        fig, ax = plt.subplots(figsize=(2.8, 2.4))
        wedges, texts, autos = ax.pie(
            vals, labels=labs, colors=cols,
            autopct='%1.0f%%', startangle=90, pctdistance=0.65,
            wedgeprops=dict(width=0.50, edgecolor='white', linewidth=2))
        for a in autos: a.set_fontsize(8); a.set_fontweight('bold')
        for t in texts: t.set_fontsize(7.5)
        ax.text(0, 0, f'{total_t}\ntareas', ha='center', va='center',
                fontsize=9, fontweight='bold', color=AZUL)
        ax.set_title('Estado de Tareas', fontsize=9,
                     fontweight='bold', color=AZUL, pad=8)
        fig.tight_layout(pad=0.3)
        return fig2rl(fig, 2.6, 2.2)

    # ── Gráfica E: Semestres ──────────────────────────────────────────────
    def g_semestres():
        if not semestres_raw: return None
        sems = [r[0] for r in semestres_raw]
        vals = [r[1] for r in semestres_raw]
        fig, ax = plt.subplots(figsize=(3.4, 2.4))
        bars = ax.bar(range(len(sems)), vals, color=DORADO,
                      edgecolor='white', width=0.55)
        ax.set_xticks(range(len(sems)))
        ax.set_xticklabels(sems, fontsize=7, rotation=20, ha='right')
        ax.set_ylabel('Alumnos', fontsize=7, color='#555')
        ax.set_title('Alumnos por Semestre', fontsize=9,
                     fontweight='bold', color=AZUL, pad=8)
        ax.yaxis.set_major_locator(plt.MaxNLocator(integer=True))
        ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)
        ax.tick_params(labelsize=7)
        for bar, val in zip(bars, vals):
            ax.text(bar.get_x()+bar.get_width()/2, val+0.03,
                    str(val), ha='center', va='bottom', fontsize=7.5, fontweight='bold')
        fig.tight_layout(pad=0.3)
        return fig2rl(fig, 3.2, 2.2)

    # Generar todas las gráficas
    img_pastel   = g_pastel()
    img_estilos  = g_barras_estilos()
    img_materias = g_materias()
    img_dona     = g_dona()
    img_sems     = g_semestres()

    # ── Estilos PDF ───────────────────────────────────────────────────────
    styles = getSampleStyleSheet()
    def ps(name, **kw):
        return ParagraphStyle(name, parent=styles['Normal'], **kw)

    s_h1    = ps('h1', fontSize=17, textColor=rl(AZUL),   fontName='Helvetica-Bold', alignment=TA_CENTER, spaceAfter=2)
    s_inst  = ps('inst', fontSize=9, textColor=colors.grey, alignment=TA_CENTER, spaceAfter=2)
    s_fecha = ps('fecha', fontSize=8, textColor=colors.grey, alignment=TA_CENTER, spaceAfter=10)
    s_rep   = ps('rep', fontSize=13, textColor=rl(DORADO),  fontName='Helvetica-Bold', alignment=TA_CENTER, spaceAfter=4)
    s_sec   = ps('sec', fontSize=11, textColor=rl(AZUL),    fontName='Helvetica-Bold', spaceBefore=10, spaceAfter=5)
    s_sub   = ps('sub', fontSize=8.5, textColor=rl(AZUL),   fontName='Helvetica-Bold', spaceBefore=6, spaceAfter=3)
    s_n     = ps('n', fontSize=8, leading=11)
    s_b     = ps('b', fontSize=8, leading=11, fontName='Helvetica-Bold')
    s_pie   = ps('pie', fontSize=6.5, textColor=colors.grey, alignment=TA_CENTER)
    s_c     = ps('c', fontSize=8, alignment=TA_CENTER)

    def mk_tabla(data, widths, hcol=AZUL):
        t = Table(data, colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle([
            ('BACKGROUND',    (0,0),(-1,0), rl(hcol)),
            ('TEXTCOLOR',     (0,0),(-1,0), colors.white),
            ('FONTNAME',      (0,0),(-1,0), 'Helvetica-Bold'),
            ('FONTSIZE',      (0,0),(-1,-1), 7.5),
            ('ROWBACKGROUNDS',(0,1),(-1,-1), [colors.white, rl(GRIS)]),
            ('GRID',          (0,0),(-1,-1), 0.3, colors.lightgrey),
            ('PADDING',       (0,0),(-1,-1), 4),
            ('VALIGN',        (0,0),(-1,-1), 'MIDDLE'),
        ]))
        return t

    def hr(col=DORADO, thick=1.5):
        return HRFlowable(width="100%", thickness=thick, color=rl(col), spaceAfter=6)

    # ── CONSTRUIR STORY ───────────────────────────────────────────────────
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter,
                            rightMargin=0.6*inch, leftMargin=0.6*inch,
                            topMargin=0.6*inch,  bottomMargin=0.6*inch)
    W = 7.3  # ancho útil en inches

    story = []

    # ══ PÁGINA 1: Portada + KPIs + Gráficas de estilos ═══════════════════
    story += [
        Paragraph("FACULTAD DE ESTUDIOS SUPERIORES CUAUTITLAN", s_h1),
        Paragraph("Universidad Nacional Autonoma de Mexico  ·  ITSE  ·  Campo 4", s_inst),
        hr(DORADO, 2),
        hr(AZUL, 0.5),
        Spacer(1, 4),
        Paragraph("REPORTE ADMINISTRATIVO GENERAL", s_rep),
        Paragraph(f"Sistema de Estilos de Aprendizaje  ·  Generado el {fecha_reporte}", s_fecha),
        Spacer(1, 6),
    ]

    # KPIs — fila única con fondo azul
    kpi_labels = ["ALUMNOS\nREGISTRADOS","PROFESORES\nACTIVOS",
                  "EVALUACIONES\nREALIZADAS","CORRECCIONES\nDE PROFES","TAREAS\nASIGNADAS"]
    kpi_vals   = [len(alumnos_db), len(profesores_db), len(evaluaciones), total_corr, len(tareas_db)]
    kpi_row1 = [Paragraph(l, ps(f'kl{i}', fontSize=6.5, textColor=colors.white,
                alignment=TA_CENTER, leading=8, fontName='Helvetica-Bold'))
                for i, l in enumerate(kpi_labels)]
    kpi_row2 = [Paragraph(str(v), ps(f'kv{i}', fontSize=18, textColor=rl(DORADO),
                alignment=TA_CENTER, fontName='Helvetica-Bold'))
                for i, v in enumerate(kpi_vals)]
    t_kpi = Table([kpi_row1, kpi_row2], colWidths=[W/5*inch]*5)
    t_kpi.setStyle(TableStyle([
        ('BACKGROUND', (0,0),(-1,-1), rl(AZUL)),
        ('ROWBACKGROUNDS',(0,0),(-1,0), [rl('#001a38')]),
        ('GRID',       (0,0),(-1,-1), 0.5, rl('#003a7a')),
        ('PADDING',    (0,0),(-1,-1), 7),
    ]))
    story += [t_kpi, Spacer(1, 10), hr(AZUL, 0.5)]

    # Sección 1: dos gráficas lado a lado + tabla detalle
    story.append(Paragraph("1. Analisis de Estilos de Aprendizaje", s_sec))
    graficas_row = []
    if img_pastel:  graficas_row.append(img_pastel)
    if img_estilos: graficas_row.append(img_estilos)
    if len(graficas_row) == 2:
        tg = Table([graficas_row], colWidths=[W/2*inch, W/2*inch])
        tg.setStyle(TableStyle([('ALIGN',(0,0),(-1,-1),'CENTER'),
                                 ('VALIGN',(0,0),(-1,-1),'MIDDLE')]))
        story.append(tg)
    elif graficas_row:
        story.append(graficas_row[0])

    # Tabla de detalle de estilos compacta
    if estilos_raw:
        story.append(Spacer(1, 6))
        total_ev = sum(r[1] for r in estilos_raw)
        est_data = [["Estilo","Evaluaciones","% del total","Correcciones","Tasa corrección"]]
        for est, cnt in estilos_raw:
            corr = corr_estilo.get(est, 0)
            tasa = f"{corr/cnt*100:.0f}%" if cnt > 0 else "0%"
            est_data.append([est.capitalize(), str(cnt),
                             f"{cnt/total_ev*100:.1f}%", str(corr), tasa])
        story.append(mk_tabla(est_data,
            [1.6*inch, 1.1*inch, 1.1*inch, 1.1*inch, 1.2*inch]))

    story.append(PageBreak())

    # ══ PÁGINA 2: Actividad académica + Estado tareas ═════════════════════
    story.append(Paragraph("2. Actividad Academica y Seguimiento de Tareas", s_sec))

    # Fila: materias | semestres | dona — las tres juntas
    fila_g2 = []
    if img_materias: fila_g2.append(img_materias)
    if img_sems:     fila_g2.append(img_sems)
    if img_dona:     fila_g2.append(img_dona)

    if fila_g2:
        ncols = len(fila_g2)
        cw = [W/ncols*inch]*ncols
        tg2 = Table([fila_g2], colWidths=cw)
        tg2.setStyle(TableStyle([('ALIGN',(0,0),(-1,-1),'CENTER'),
                                  ('VALIGN',(0,0),(-1,-1),'MIDDLE')]))
        story.append(tg2)

    # Tabla resumen de materias
    if materias_raw:
        story += [Spacer(1,8), Paragraph("Detalle de materias evaluadas:", s_sub)]
        mat_data = [["Materia","No. Evaluaciones","% del total"]]
        tot_mat = sum(r[1] for r in materias_raw)
        for mat, cnt in materias_raw:
            mat_data.append([mat, str(cnt), f"{cnt/tot_mat*100:.1f}%"])
        story.append(mk_tabla(mat_data, [3.8*inch, 1.5*inch, 1.5*inch]))

    # Tabla resumen de semestres
    if semestres_raw:
        story += [Spacer(1,8), Paragraph("Distribucion de alumnos por semestre:", s_sub)]
        sem_data = [["Semestre","Alumnos","% del total"]]
        tot_al = len(alumnos_db)
        for sem, cnt in semestres_raw:
            sem_data.append([sem, str(cnt), f"{cnt/tot_al*100:.1f}%" if tot_al else "—"])
        story.append(mk_tabla(sem_data, [2.5*inch, 1.5*inch, 1.5*inch]))

    story.append(PageBreak())

    # ══ PÁGINA 3: Padrón de alumnos ══════════════════════════════════════
    story.append(Paragraph("3. Padron de Alumnos", s_sec))
    al_data = [["#","Nombre","No. Cuenta","Semestre","Materias eval."]]
    for i, al in enumerate(alumnos_db, 1):
        mats = eval_por_cuenta.get(al["cuenta"], [])
        al_data.append([str(i), al["nombre"], al["cuenta"],
                        al["semestre"] or "—", str(len(mats))])
    story.append(mk_tabla(al_data, [0.3*inch, 2.6*inch, 1.1*inch, 1.3*inch, 1.0*inch]))
    story.append(Spacer(1,10))

    story.append(Paragraph("Detalle de evaluaciones por alumno:", s_sub))
    for al in alumnos_db:
        evals = [e for e in evaluaciones if e["cuenta"] == al["cuenta"]]
        if not evals: continue
        ev_data = [["Materia","Estilo","Estado","Profesor corrector"]]
        for ev in evals:
            ev_data.append([
                Paragraph(ev["materia"], s_n),
                ev["estilo"].capitalize(),
                "Corregida" if ev["recomendacion_corregida"] else "IA original",
                ev["profesor"] or "—"
            ])
        story.append(KeepTogether([
            Paragraph(f"{al['nombre']}  ·  {al['cuenta']}  ·  {al['semestre'] or '—'}", s_b),
            Spacer(1,2),
            mk_tabla(ev_data, [2.8*inch, 1.0*inch, 1.2*inch, 1.8*inch]),
            Spacer(1,7),
        ]))

    story.append(PageBreak())

    # ══ PÁGINA 4: Profesores + Tareas ════════════════════════════════════
    story.append(Paragraph("4. Padron de Profesores", s_sec))
    pr_data = [["#","Nombre completo","Usuario"]]
    for i, p in enumerate(profesores_db, 1):
        pr_data.append([str(i), p["nombre"], p["usuario"]])
    story.append(mk_tabla(pr_data, [0.4*inch, 4.1*inch, 2.1*inch]))

    if tareas_db:
        story += [Spacer(1,12), Paragraph("5. Tareas Asignadas por Profesores", s_sec)]
        t_data = [["Titulo","Materia","Alumno","Profesor","F. Entrega","Entregas recib."]]
        for t in tareas_db:
            t_data.append([
                Paragraph(t["titulo"], s_n),
                Paragraph(t["materia"], s_n),
                Paragraph(t["nombre_alumno"] or "—", s_n),
                t["profesor"],
                t["fecha_entrega"],
                str(t["total_entregas"])
            ])
        story.append(mk_tabla(t_data,
            [1.5*inch, 1.5*inch, 1.2*inch, 1.1*inch, 0.85*inch, 0.85*inch]))

    # Pie de página
    story += [
        Spacer(1, 16),
        hr(DORADO, 1),
        Paragraph(
            f"Documento generado automaticamente — Sistema de Estilos de Aprendizaje — FESC Campo 4 — {fecha_reporte}",
            s_pie),
    ]

    doc.build(story)
    buffer.seek(0)
    from flask import send_file as sf
    nombre = f"Reporte_Administrativo_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
    return sf(buffer, as_attachment=True, download_name=nombre, mimetype='application/pdf')


if __name__ == "__main__":
    app.run(debug=True)