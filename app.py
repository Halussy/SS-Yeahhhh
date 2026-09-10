from flask import Flask, render_template, request, session, redirect, url_for, jsonify, send_from_directory, send_file
from flask_wtf import CSRFProtect
from flask_wtf.csrf import CSRFError
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from Estilos_Apren import EvaluadorEstilosAprendizaje
import sqlite3
from datetime import timedelta
import google.genai as genai
from google.genai import types as genai_types
import os
import io
import json
import random
import secrets
import string
import unicodedata
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

# Se importan aquí (en vez de dentro de admin_reporte) para que la construcción del
# cache de fuentes de Matplotlib ocurra una sola vez al arrancar el servidor, no en
# la primera petición al reporte (donde puede tardar hasta ~1 minuto y parecer que
# la app se colgó).
import matplotlib
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
clave_secreta_env = os.getenv("SECRET_KEY")
if not clave_secreta_env:
    clave_secreta_env = secrets.token_hex(32)
    print("ADVERTENCIA: SECRET_KEY no configurada en .env — usando una clave temporal generada en este arranque "
          "(las sesiones se invalidarán al reiniciar el servidor). Define SECRET_KEY en tu .env para producción.")
app.secret_key = clave_secreta_env

csrf = CSRFProtect(app)

UPLOAD_FOLDER = 'uploads_tareas'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10 MB por subida
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'png', 'jpg', 'jpeg', 'txt', 'zip'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
app.permanent_session_lifetime = timedelta(minutes=10)

@app.errorhandler(413)
def archivo_demasiado_grande(e):
    return "El archivo supera el límite permitido de 10 MB. Vuelve a la página anterior e inténtalo con un archivo más pequeño.", 413

@app.errorhandler(CSRFError)
def token_csrf_invalido(e):
    return "Tu formulario expiró o la sesión venció. Vuelve a la página anterior, recarga e inténtalo de nuevo.", 400

api_key_secreta = os.getenv("GEMINI_API_KEY")
cliente_ia = genai.Client(api_key=api_key_secreta)

mi_evaluador = EvaluadorEstilosAprendizaje()

BASE_DE_DATOS = {}

# Carreras ofertadas por el plantel. Para agregar una carrera nueva: añadir su clave aquí
# y su plan de estudios correspondiente en PLANES_DE_ESTUDIO. No renombrar ni eliminar una
# clave existente si ya hay alumnos dados de alta con esa carrera.
CARRERAS = {
    "ITSE": "Ingeniería en Telecomunicaciones, Sistemas y Electrónica",
    "CONT": "Contaduría",
    "ADMON": "Administración",
    "IME": "Ingeniería Mecánica Eléctrica",
    "DCV": "Diseño y Comunicación Visual",
    "INDUSTRIAL": "Ingeniería Industrial",
    "INFORMATICA": "Informática",
    "AGRICOLA": "Ingeniería Agrícola",
    "MVZ": "Medicina Veterinaria y Zootecnia",
}

PLANES_DE_ESTUDIO = {
    "ITSE": {
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
    },

    # Fuente: Plan 2008 — https://07156d37-2c43-4621-93a9-a6abd9275020.filesusr.com/ugd/3b4ada_b51de36a8cc941f5a5725e5ad807ce33.pdf
    # 416 créditos totales (incluye 40 créditos optativos de un banco de 26 materias
    # no detalladas en el documento fuente, por eso no están aquí).
    "CONT": {
        "1er Semestre": [
            {"nombre": "Contabilidad Básica", "creditos": 12},
            {"nombre": "Taller Aplicado a Contabilidad Básica", "creditos": 2},
            {"nombre": "Introducción a los Enfoques Administrativos", "creditos": 12},
            {"nombre": "Introducción al Estudio del Derecho", "creditos": 8},
            {"nombre": "Fundamentos Matemáticos para Ciencias Administrativas", "creditos": 10},
            {"nombre": "Herramientas Básicas de Cómputo", "creditos": 8}
        ],
        "2do Semestre": [
            {"nombre": "Contabilidad Intermedia", "creditos": 12},
            {"nombre": "Taller de Contabilidad Intermedia", "creditos": 2},
            {"nombre": "Tendencias Administrativas Contemporáneas", "creditos": 10},
            {"nombre": "Derecho Constitucional y Administrativo", "creditos": 8},
            {"nombre": "Matemáticas Financieras", "creditos": 10},
            {"nombre": "Fundamentos del Comportamiento Humano", "creditos": 8},
            {"nombre": "Redacción", "creditos": 4}
        ],
        "3er Semestre": [
            {"nombre": "Contabilidad Superior", "creditos": 12},
            {"nombre": "Taller Aplicado a Contabilidad Superior", "creditos": 2},
            {"nombre": "Administración de Recursos Humanos", "creditos": 6},
            {"nombre": "Derecho Mercantil", "creditos": 8},
            {"nombre": "Estadística Descriptiva", "creditos": 10},
            {"nombre": "Economía y Globalización", "creditos": 6},
            {"nombre": "Ética y Valores", "creditos": 4}
        ],
        "4to Semestre": [
            {"nombre": "Contabilidad de Sociedades", "creditos": 8},
            {"nombre": "Fundamentos de Costos y Costos Históricos", "creditos": 12},
            {"nombre": "Taller Aplicado a Fundamentos de Costos y Costos Históricos", "creditos": 2},
            {"nombre": "Derecho Laboral", "creditos": 8},
            {"nombre": "Inferencia Estadística", "creditos": 10},
            {"nombre": "Macroeconomía", "creditos": 6}
        ],
        "5to Semestre": [
            {"nombre": "Fundamentos Financieros", "creditos": 10},
            {"nombre": "Producción Conjunta y Costos Estimados", "creditos": 12},
            {"nombre": "Taller Aplicado a Producción Conjunta", "creditos": 2},
            {"nombre": "Derecho Fiscal", "creditos": 8},
            {"nombre": "Metodología de la Investigación", "creditos": 8},
            {"nombre": "Microeconomía", "creditos": 6}
        ],
        "6to Semestre": [
            {"nombre": "Planeación y Control Financiero", "creditos": 10},
            {"nombre": "Costos Estándar y Costo Directo", "creditos": 12},
            {"nombre": "Taller Aplicado a Costos Estándar y Costo Directo", "creditos": 2},
            {"nombre": "Estudio Fiscal de las Personas Morales", "creditos": 10},
            {"nombre": "Fundamentos de Auditoría", "creditos": 10},
            {"nombre": "Nómina y Contribuciones de Seguridad Social", "creditos": 6}
        ],
        "7mo Semestre": [
            {"nombre": "Formulación y Evaluación de Proyecto de Inversión", "creditos": 10},
            {"nombre": "Administración Pública", "creditos": 8},
            {"nombre": "Emprendedores", "creditos": 8},
            {"nombre": "Estudio Fiscal de las Personas Físicas", "creditos": 10},
            {"nombre": "Auditoría a los Estados Financieros", "creditos": 8},
            {"nombre": "Normatividad Ética del Lic. en Contaduría", "creditos": 4}
        ],
        "8vo Semestre": [
            {"nombre": "Dictamen de los Estados Financieros", "creditos": 8}
        ],
        "8vo-9no Semestre - Módulo: Auditoría": [
            {"nombre": "Auditoría Fiscal", "creditos": 8},
            {"nombre": "Contraloría", "creditos": 8},
            {"nombre": "Código Fiscal de la Federación", "creditos": 8}
        ],
        "8vo-9no Semestre - Módulo: Comercio Exterior": [
            {"nombre": "Impuestos de Importación y Exportación", "creditos": 8},
            {"nombre": "Aspectos Fiscales de los Tratados Internacionales", "creditos": 8},
            {"nombre": "Legislación Aduanal", "creditos": 8}
        ],
        "8vo-9no Semestre - Módulo: Finanzas": [
            {"nombre": "Administración Financiera", "creditos": 8},
            {"nombre": "Finanzas Internacionales", "creditos": 8},
            {"nombre": "Ingeniería Financiera y Mercado de Divisas", "creditos": 8}
        ],
        "8vo-9no Semestre - Módulo: Fiscal": [
            {"nombre": "Código Fiscal de la Federación", "creditos": 8},
            {"nombre": "Tópicos Fiscales", "creditos": 8},
            {"nombre": "Derecho Penal Fiscal", "creditos": 8}
        ],
        "8vo-9no Semestre - Módulo: Costos": [
            {"nombre": "Administración de la Calidad", "creditos": 8},
            {"nombre": "El Costo: Evolución e Impacto", "creditos": 8},
            {"nombre": "Análisis de la Tendencia del Costo", "creditos": 8}
        ]
    },

    # Fuente: Plan 2009 — https://www.cuautitlan.unam.mx/licenciaturas/administracion/descargas/Mapa_curricular.pdf
    # (dominio oficial FESC). El documento solo cubre 7 semestres: para 8vo y 9no
    # únicamente indica "dos optativas del área profesionalizante más dos optativas
    # de elección" sin nombrarlas ni asignarles créditos — pendiente hasta confirmar
    # con la coordinación o localizar el documento que las liste.
    "ADMON": {
        "1er Semestre": [
            {"nombre": "Teorías y Funciones de la Administración", "creditos": 10},
            {"nombre": "Tecnologías de la Información y la Comunicación", "creditos": 8},
            {"nombre": "Matemáticas Aplicadas a la Administración", "creditos": 10},
            {"nombre": "Fundamentos de Contabilidad", "creditos": 10},
            {"nombre": "Derecho Civil y Mercantil", "creditos": 8},
            {"nombre": "Desarrollo de Hab. de la Comunicación Adtiva.", "creditos": 10}
        ],
        "2do Semestre": [
            {"nombre": "Administración del Capital Humano", "creditos": 10},
            {"nombre": "Contabilidad Financiera", "creditos": 10},
            {"nombre": "Gestión Administrativa", "creditos": 10},
            {"nombre": "Lectura y Análisis de Textos Administrativos", "creditos": 6},
            {"nombre": "Derecho Constitucional y Administrativo", "creditos": 8},
            {"nombre": "Matemáticas Financieras", "creditos": 10}
        ],
        "3er Semestre": [
            {"nombre": "Administración de Organizaciones", "creditos": 8},
            {"nombre": "Administración de Prestaciones", "creditos": 6},
            {"nombre": "Contabilidad de Costos", "creditos": 10},
            {"nombre": "Estadística Descriptiva y Probabilidad", "creditos": 10},
            {"nombre": "Ética y Valores", "creditos": 6},
            {"nombre": "Derecho Laboral", "creditos": 8}
        ],
        "4to Semestre": [
            {"nombre": "Introducción a las Finanzas y Proyectos de Inversión", "creditos": 10},
            {"nombre": "Modelos Organizacionales", "creditos": 6},
            {"nombre": "Sistemas de Información Automatizados en las Organizaciones", "creditos": 8},
            {"nombre": "Sistemas de Evaluación del Capital Humano", "creditos": 10},
            {"nombre": "Inferencia Estadística", "creditos": 10}
        ],
        "5to Semestre": [
            {"nombre": "Metodología de la Investigación", "creditos": 6},
            {"nombre": "Administración de Evaluación de Inversiones", "creditos": 10},
            {"nombre": "Administración Estratégica", "creditos": 10},
            {"nombre": "Derecho Penal y Fiscal", "creditos": 8},
            {"nombre": "Investigación de Operaciones", "creditos": 10},
            {"nombre": "Teoría de la Calidad", "creditos": 8},
            {"nombre": "Microeconomía", "creditos": 6}
        ],
        "6to Semestre": [
            {"nombre": "Administración de la Producción", "creditos": 10},
            {"nombre": "Desarrollo Sustentable", "creditos": 4},
            {"nombre": "Fundamentos de Mercadotecnia", "creditos": 10},
            {"nombre": "Sistemas de Aseguramiento de la Calidad", "creditos": 10},
            {"nombre": "Macroeconomía", "creditos": 6},
            {"nombre": "Auditoría Administrativa", "creditos": 8}
        ],
        "7mo Semestre": [
            {"nombre": "Administración de Operaciones", "creditos": 10},
            {"nombre": "Análisis Socioeconómico de México", "creditos": 6},
            {"nombre": "Desarrollo de Emprendedores", "creditos": 8},
            {"nombre": "Investigación de Mercados", "creditos": 8},
            {"nombre": "Logística", "creditos": 8}
        ]
    },

    # Fuente: Descripción Sintética oficial DGAE — https://escolar1.unam.mx/planes/fes_cuautli/Ingmec-ele_cuautitlan.pdf
    # (aprobado 09/mar/2011). El 9no semestre no agrupa sus materias en módulos con
    # nombre propio: son dos bolsas libres (elegir 3 de "Obligatorias de Elección" +
    # 2 de "Optativas"), tal como indica el documento fuente.
    "IME": {
        "1er Semestre": [
            {"nombre": "Álgebra", "creditos": 8},
            {"nombre": "Cálculo Diferencial e Integral", "creditos": 8},
            {"nombre": "Computación para Ingeniería", "creditos": 8},
            {"nombre": "Geometría Analítica", "creditos": 8},
            {"nombre": "Química", "creditos": 8},
            {"nombre": "Comunicación Oral y Escrita", "creditos": 6}
        ],
        "2do Semestre": [
            {"nombre": "Álgebra Lineal", "creditos": 6},
            {"nombre": "Cálculo Vectorial", "creditos": 8},
            {"nombre": "Dibujo", "creditos": 4},
            {"nombre": "Estática", "creditos": 8},
            {"nombre": "Tecnología de Materiales", "creditos": 10},
            {"nombre": "Termodinámica", "creditos": 10}
        ],
        "3er Semestre": [
            {"nombre": "Termodinámica Aplicada", "creditos": 8},
            {"nombre": "Ecuaciones Diferenciales", "creditos": 6},
            {"nombre": "Cinemática y Dinámica", "creditos": 10},
            {"nombre": "Electricidad y Magnetismo", "creditos": 10},
            {"nombre": "Ética y Liderazgo", "creditos": 6},
            {"nombre": "Programación Aplicada a la Ingeniería", "creditos": 8}
        ],
        "4to Semestre": [
            {"nombre": "Análisis de Circuitos Eléctricos", "creditos": 10},
            {"nombre": "Dinámica de Sistemas Físicos", "creditos": 6},
            {"nombre": "Mecánica de Fluidos", "creditos": 8},
            {"nombre": "Mecánica de Sólidos", "creditos": 8},
            {"nombre": "Métodos Numéricos", "creditos": 8},
            {"nombre": "Probabilidad y Estadística", "creditos": 8}
        ],
        "5to Semestre": [
            {"nombre": "Ingeniería de Materiales", "creditos": 10},
            {"nombre": "Electrónica Básica", "creditos": 10},
            {"nombre": "Medición e Instrumentación Eléctrica", "creditos": 6},
            {"nombre": "Metodología de la Investigación", "creditos": 6},
            {"nombre": "Diseño de Elementos de Máquinas", "creditos": 8},
            {"nombre": "Costos y Evaluación Económica", "creditos": 8}
        ],
        "6to Semestre": [
            {"nombre": "Turbomaquinaria", "creditos": 8},
            {"nombre": "Control Electromecánico", "creditos": 8},
            {"nombre": "Mecanismos", "creditos": 8},
            {"nombre": "Transformadores y Motores de Inducción", "creditos": 10},
            {"nombre": "Procesos de Conformado de Materiales", "creditos": 10}
        ],
        "7mo Semestre": [
            {"nombre": "Laboratorio de Máquinas Térmicas", "creditos": 4},
            {"nombre": "Laboratorio de Mecánica de Fluidos", "creditos": 4},
            {"nombre": "Máquinas de Desplazamiento Positivo", "creditos": 8},
            {"nombre": "Dinámica de Maquinaria", "creditos": 8},
            {"nombre": "Máquinas de Corriente Directa y Máquinas Síncronas", "creditos": 10},
            {"nombre": "Procesos de Corte de Materiales", "creditos": 10}
        ],
        "8vo Semestre": [
            {"nombre": "Transferencia de Calor", "creditos": 8},
            {"nombre": "Diseño por Computadora", "creditos": 4},
            {"nombre": "Ingeniería Ecológica", "creditos": 8},
            {"nombre": "Instalaciones Eléctricas", "creditos": 8},
            {"nombre": "Sistemas Eléctricos de Potencia I", "creditos": 8},
            {"nombre": "Teoría de Control y Robótica", "creditos": 10}
        ],
        "9no Semestre": [
            {"nombre": "Gestión Gerencial", "creditos": 6}
        ],
        "9no Semestre - Obligatorias de Elección": [
            {"nombre": "Metalurgia Mecánica", "creditos": 8},
            {"nombre": "Aire Acondicionado y Refrigeración", "creditos": 8},
            {"nombre": "Fuentes Alternas de Energía", "creditos": 8},
            {"nombre": "Plantas de Generación Convencionales", "creditos": 8},
            {"nombre": "Diseño de Máquinas", "creditos": 8},
            {"nombre": "Manufactura por Computadora", "creditos": 8},
            {"nombre": "Diseño de Iluminación por Computadora", "creditos": 8},
            {"nombre": "Iluminación Exterior", "creditos": 8},
            {"nombre": "Iluminación Interior", "creditos": 8},
            {"nombre": "Análisis y Diseño de Sistemas", "creditos": 8},
            {"nombre": "Control por Computadora de Sistemas Mecatrónicos", "creditos": 8},
            {"nombre": "Microcontroladores", "creditos": 8},
            {"nombre": "Protección de Sistemas Eléctricos", "creditos": 8},
            {"nombre": "Sistemas Eléctricos de Potencia II", "creditos": 8},
            {"nombre": "Subestaciones Eléctricas", "creditos": 8},
            {"nombre": "Control y Monitoreo de la Energía", "creditos": 8},
            {"nombre": "Sistemas de Distribución", "creditos": 8}
        ],
        "9no Semestre - Optativas": [
            {"nombre": "Análisis por Elementos Finitos", "creditos": 8},
            {"nombre": "Aprovechamiento de la Energía Solar", "creditos": 8},
            {"nombre": "Automatización Industrial", "creditos": 8},
            {"nombre": "Cogeneración", "creditos": 8},
            {"nombre": "Diseño de Herramental", "creditos": 8},
            {"nombre": "Diseño y Modelación de Equipos Térmicos", "creditos": 8},
            {"nombre": "Electrónica de Potencia", "creditos": 8},
            {"nombre": "Emprendedores", "creditos": 8},
            {"nombre": "Flujo de Potencia", "creditos": 8},
            {"nombre": "Iluminación Áreas Deportivas", "creditos": 8},
            {"nombre": "Iluminación Arquitectónica", "creditos": 8},
            {"nombre": "Inteligencia Artificial", "creditos": 8},
            {"nombre": "Plantas Generadoras", "creditos": 8},
            {"nombre": "Programación Lógica", "creditos": 8},
            {"nombre": "Robótica Aplicada", "creditos": 8},
            {"nombre": "Sistemas de Transporte Eléctrico", "creditos": 8},
            {"nombre": "Técnicas de Ahorro de Energía", "creditos": 8},
            {"nombre": "Teoría de la Calidad", "creditos": 8},
            {"nombre": "Termoeconomía", "creditos": 8},
            {"nombre": "Vibraciones Mecánicas", "creditos": 8},
            {"nombre": "Ingeniería de Procesos Industriales", "creditos": 8}
        ]
    },

    # Fuente: Descripción Sintética oficial DGAE, Sistema Escolarizado — https://escolar1.unam.mx/planes/fes_cuautli/Dise%F1Com-Cuau.pdf
    # (actualizado 19/may/2010). Del 7mo al 8vo semestre el alumno elige 1 de 3
    # orientaciones (cada una con materias fijas de ambos semestres + 5 optativas
    # por semestre de una lista propia). Hay además un banco de optativas comunes
    # a las 3 orientaciones y un bloque de asignaturas extracurriculares sin créditos.
    "DCV": {
        "1er Semestre": [
            {"nombre": "Arte Antiguo", "creditos": 6},
            {"nombre": "Dibujo I", "creditos": 12},
            {"nombre": "Diseño I", "creditos": 8},
            {"nombre": "Geometría I", "creditos": 4},
            {"nombre": "Metodología de la Investigación I", "creditos": 4},
            {"nombre": "Teoría de la Imagen I", "creditos": 4},
            {"nombre": "Teoría de la Comunicación I", "creditos": 6},
            {"nombre": "Teoría del Arte I", "creditos": 4}
        ],
        "2do Semestre": [
            {"nombre": "Arte Precolombino", "creditos": 6},
            {"nombre": "Dibujo II", "creditos": 12},
            {"nombre": "Diseño II", "creditos": 8},
            {"nombre": "Geometría II", "creditos": 4},
            {"nombre": "Metodología de la Investigación II", "creditos": 4},
            {"nombre": "Teoría de la Imagen II", "creditos": 4},
            {"nombre": "Teoría de la Comunicación II", "creditos": 6},
            {"nombre": "Teoría del Arte II", "creditos": 4}
        ],
        "3er Semestre": [
            {"nombre": "Arte de la Edad Media y Renacimiento", "creditos": 6},
            {"nombre": "Dibujo III", "creditos": 12},
            {"nombre": "Diseño III", "creditos": 8},
            {"nombre": "Fotografía I", "creditos": 8},
            {"nombre": "Técnicas y Sistemas de Impresión I", "creditos": 8},
            {"nombre": "Introducción a la Tecnología Digital I", "creditos": 9},
            {"nombre": "Teoría de la Comunicación III", "creditos": 6},
            {"nombre": "Economía para la Comunicación Visual", "creditos": 6}
        ],
        "4to Semestre": [
            {"nombre": "Arte Barroco y Virreinal", "creditos": 6},
            {"nombre": "Dibujo IV", "creditos": 12},
            {"nombre": "Diseño IV", "creditos": 8},
            {"nombre": "Fotografía II", "creditos": 8},
            {"nombre": "Técnicas y Sistemas de Impresión II", "creditos": 8},
            {"nombre": "Introducción a la Tecnología Digital II", "creditos": 9},
            {"nombre": "Teoría de la Comunicación IV", "creditos": 6},
            {"nombre": "Imagen y Sociedad", "creditos": 6}
        ],
        "5to Semestre": [
            {"nombre": "Arte del Siglo XIX al XX", "creditos": 6},
            {"nombre": "Administración en la Comunicación Visual", "creditos": 6},
            {"nombre": "Diseño V", "creditos": 8},
            {"nombre": "Fotografía III", "creditos": 6},
            {"nombre": "Laboratorio de Diseño Editorial I", "creditos": 8},
            {"nombre": "Medios de Comunicación I", "creditos": 4},
            {"nombre": "Producción Audiovisual I", "creditos": 5},
            {"nombre": "Semiótica I", "creditos": 6}
        ],
        "6to Semestre": [
            {"nombre": "Arte Contemporáneo", "creditos": 6},
            {"nombre": "Mercadotecnia en la Comunicación Visual", "creditos": 6},
            {"nombre": "Diseño VI", "creditos": 8},
            {"nombre": "Fotografía IV", "creditos": 6},
            {"nombre": "Laboratorio de Diseño Editorial II", "creditos": 8},
            {"nombre": "Medios de Comunicación II", "creditos": 4},
            {"nombre": "Producción Audiovisual II", "creditos": 5},
            {"nombre": "Semiótica II", "creditos": 6}
        ],
        "7mo-8vo Semestre - Orientación: Audiovisual, Fotografía y Multimedia": [
            {"nombre": "Dirección de Arte I", "creditos": 8},
            {"nombre": "Fotografía Especializada I", "creditos": 8},
            {"nombre": "Multimedia I", "creditos": 8},
            {"nombre": "Dirección de Arte II", "creditos": 8},
            {"nombre": "Fotografía Especializada II", "creditos": 8},
            {"nombre": "Multimedia II", "creditos": 8},
            {"nombre": "Teoría e Historia de los Sistemas Audiovisuales", "creditos": 4},
            {"nombre": "Teoría e Historia de la Fotografía", "creditos": 4},
            {"nombre": "Fotografía Digital I", "creditos": 4},
            {"nombre": "Fotografía Experimental", "creditos": 4},
            {"nombre": "Iluminación Fotográfica I", "creditos": 4},
            {"nombre": "Producción Audiovisual III", "creditos": 4},
            {"nombre": "Animación", "creditos": 4},
            {"nombre": "Animación Digital", "creditos": 4},
            {"nombre": "Fotografía Digital II", "creditos": 4},
            {"nombre": "Fotografía Experimental / Procesos Antiguos", "creditos": 4},
            {"nombre": "Iluminación Fotográfica II", "creditos": 4},
            {"nombre": "Producción Audiovisual IV", "creditos": 4}
        ],
        "7mo-8vo Semestre - Orientación: Diseño Editorial e Ilustración": [
            {"nombre": "Laboratorio de Diseño Editorial III", "creditos": 8},
            {"nombre": "Autoedición I", "creditos": 8},
            {"nombre": "Ilustración I", "creditos": 8},
            {"nombre": "Laboratorio de Diseño Editorial IV", "creditos": 8},
            {"nombre": "Autoedición II", "creditos": 8},
            {"nombre": "Ilustración II", "creditos": 8},
            {"nombre": "Teoría e Historia del Diseño Editorial", "creditos": 4},
            {"nombre": "Teoría e Historia de la Ilustración", "creditos": 4},
            {"nombre": "Dibujo V", "creditos": 4},
            {"nombre": "Ilustración Digital I", "creditos": 4},
            {"nombre": "Sistemas de Impresión Editorial I", "creditos": 4},
            {"nombre": "Caricatura", "creditos": 4},
            {"nombre": "Publicidad", "creditos": 4},
            {"nombre": "Relaciones Públicas", "creditos": 4},
            {"nombre": "Dibujo VI", "creditos": 4},
            {"nombre": "Ilustración Digital II", "creditos": 4},
            {"nombre": "Sistemas de Impresión Editorial II", "creditos": 4},
            {"nombre": "Historieta", "creditos": 4}
        ],
        "7mo-8vo Semestre - Orientación: Simbología y Diseño en Soportes Tridimensionales": [
            {"nombre": "Diseño VII", "creditos": 8},
            {"nombre": "Diseño Digital I", "creditos": 8},
            {"nombre": "Envase y Embalaje I", "creditos": 8},
            {"nombre": "Diseño VIII", "creditos": 8},
            {"nombre": "Diseño Digital II", "creditos": 8},
            {"nombre": "Envase y Embalaje II", "creditos": 8},
            {"nombre": "Teoría e Historia del Diseño", "creditos": 4},
            {"nombre": "Taller de Serigrafía I", "creditos": 4},
            {"nombre": "Estrategia de Medios I", "creditos": 4},
            {"nombre": "Ingeniería con Papel I", "creditos": 4},
            {"nombre": "Ilustración Tridimensional I", "creditos": 4},
            {"nombre": "Teoría del Conocimiento Visual I", "creditos": 4},
            {"nombre": "Relaciones Humanas", "creditos": 4},
            {"nombre": "Taller de Serigrafía II", "creditos": 4},
            {"nombre": "Estrategia de Medios II", "creditos": 4},
            {"nombre": "Ingeniería con Papel II", "creditos": 4},
            {"nombre": "Ilustración Tridimensional II", "creditos": 4},
            {"nombre": "Teoría del Conocimiento Visual II", "creditos": 4}
        ],
        "Optativas Comunes a las Orientaciones": [
            {"nombre": "Procesos de Comunicación I", "creditos": 4},
            {"nombre": "Psicología para la Comunicación Visual I", "creditos": 4},
            {"nombre": "Régimen Legal de la Comunicación Visual I", "creditos": 4},
            {"nombre": "Hermenéutica y Comunicación Visual", "creditos": 4},
            {"nombre": "Procesos de Comunicación II", "creditos": 4},
            {"nombre": "Psicología para la Comunicación Visual II", "creditos": 4},
            {"nombre": "Régimen Legal de la Comunicación Visual II", "creditos": 4}
        ],
        "9no Semestre": [
            {"nombre": "Ética para la Comunicación Visual", "creditos": 0},
            {"nombre": "Seminario Integral de Investigación Profesional", "creditos": 22}
        ],
        "Asignaturas Extracurriculares": [
            {"nombre": "Redacción y Análisis de Textos I", "creditos": 0},
            {"nombre": "Ética para la Comunicación Visual", "creditos": 0},
            {"nombre": "Redacción y Análisis de Textos II", "creditos": 0}
        ]
    },

    # Fuente: https://escolar1.unam.mx/planes/fes_cuautli/ing_industrial.pdf (aprobado 17/jun/2011).
    # El 9no semestre combina 1 materia fija + 1 módulo de "Obligatoria de Elección
    # por Profundización" (elegir 1 de 5, 3 materias c/u) + 2 optativas libres.
    "INDUSTRIAL": {
        "1er Semestre": [
            {"nombre": "Álgebra", "creditos": 8},
            {"nombre": "Cálculo Diferencial e Integral", "creditos": 8},
            {"nombre": "Computación para Ingeniería", "creditos": 8},
            {"nombre": "Geometría Analítica", "creditos": 8},
            {"nombre": "Química", "creditos": 8},
            {"nombre": "Comunicación Oral y Escrita", "creditos": 6}
        ],
        "2do Semestre": [
            {"nombre": "Álgebra Lineal", "creditos": 6},
            {"nombre": "Cálculo Vectorial", "creditos": 8},
            {"nombre": "Dibujo", "creditos": 4},
            {"nombre": "Estática", "creditos": 8},
            {"nombre": "Introducción a la Tecnología de Materiales", "creditos": 10},
            {"nombre": "Termodinámica", "creditos": 10}
        ],
        "3er Semestre": [
            {"nombre": "Ecuaciones Diferenciales", "creditos": 6},
            {"nombre": "Cinemática y Dinámica", "creditos": 10},
            {"nombre": "Electricidad y Magnetismo", "creditos": 10},
            {"nombre": "Ética y Liderazgo", "creditos": 6},
            {"nombre": "Programación Aplicada a la Ingeniería", "creditos": 8},
            {"nombre": "Estudio del Trabajo", "creditos": 10}
        ],
        "4to Semestre": [
            {"nombre": "Fundamentos de Mecánica de Sólidos", "creditos": 8},
            {"nombre": "Ingeniería Eléctrica Industrial", "creditos": 8},
            {"nombre": "Ingeniería y Productividad", "creditos": 8},
            {"nombre": "Psicología Industrial", "creditos": 6},
            {"nombre": "Termofluidos", "creditos": 10},
            {"nombre": "Probabilidad y Estadística", "creditos": 8}
        ],
        "5to Semestre": [
            {"nombre": "Electrónica Industrial", "creditos": 10},
            {"nombre": "Procesos de Manufactura", "creditos": 10},
            {"nombre": "Técnicas de Evaluación Económica", "creditos": 8},
            {"nombre": "Diseño de Elementos de Máquinas", "creditos": 8},
            {"nombre": "Procesos Industriales", "creditos": 8}
        ],
        "6to Semestre": [
            {"nombre": "Seguridad e Higiene Industrial", "creditos": 6},
            {"nombre": "Máquinas Eléctricas", "creditos": 10},
            {"nombre": "Diseño de Sistemas Productivos", "creditos": 8},
            {"nombre": "Diseño y Manufactura por Computadora", "creditos": 10},
            {"nombre": "Estadística Avanzada Industrial", "creditos": 8}
        ],
        "7mo Semestre": [
            {"nombre": "Aspectos Básicos en el Desarrollo Empresarial", "creditos": 6},
            {"nombre": "Gestión de Empresas", "creditos": 8},
            {"nombre": "Instalaciones Electromecánicas", "creditos": 10},
            {"nombre": "Investigación de Operaciones I", "creditos": 8},
            {"nombre": "Planeación y Control de la Producción", "creditos": 10}
        ],
        "8vo Semestre": [
            {"nombre": "Cadena de Suministro", "creditos": 8},
            {"nombre": "Elaboración y Evaluación de Proyectos", "creditos": 8},
            {"nombre": "Relaciones Laborales y Comportamiento Humano", "creditos": 6},
            {"nombre": "Ingeniería Ecológica", "creditos": 8},
            {"nombre": "Automatización y Robótica", "creditos": 10}
        ],
        "9no Semestre": [
            {"nombre": "Manufactura Esbelta", "creditos": 8}
        ],
        "9no Semestre - Módulo: Mantenimiento": [
            {"nombre": "Administración del Mantenimiento", "creditos": 8},
            {"nombre": "Cambio Rápido de Herramientas (SMED)", "creditos": 8},
            {"nombre": "Mantenimiento Productivo Total (TPM)", "creditos": 8}
        ],
        "9no Semestre - Módulo: Logística": [
            {"nombre": "Distribución y Transporte", "creditos": 8},
            {"nombre": "Gerencia de Operaciones", "creditos": 8},
            {"nombre": "Logística Industrial", "creditos": 8}
        ],
        "9no Semestre - Módulo: Calidad": [
            {"nombre": "Análisis de Calidad con Software Estadístico", "creditos": 8},
            {"nombre": "Gestión de Calidad", "creditos": 8},
            {"nombre": "Métodos Estadísticos Avanzados", "creditos": 8}
        ],
        "9no Semestre - Módulo: Automatización Industrial": [
            {"nombre": "Cambio Rápido de Herramientas (SMED)", "creditos": 8},
            {"nombre": "Manufactura Integrada por Computadora", "creditos": 8},
            {"nombre": "Sistemas de Manufactura Flexible", "creditos": 8}
        ],
        "9no Semestre - Módulo: Producción": [
            {"nombre": "Desarrollo y Diseño de un Servicio", "creditos": 8},
            {"nombre": "Ergonomía", "creditos": 8},
            {"nombre": "Investigación de Operaciones II", "creditos": 8}
        ],
        "9no Semestre - Optativas": [
            {"nombre": "Administración de Mantenimiento", "creditos": 8},
            {"nombre": "Aplicaciones de Manufactura Esbelta", "creditos": 8},
            {"nombre": "Automatización de Procesos Industriales", "creditos": 8},
            {"nombre": "Comercio Internacional", "creditos": 8},
            {"nombre": "Desarrollo de Habilidades Gerenciales", "creditos": 8},
            {"nombre": "Desarrollo y Diseño de Servicio", "creditos": 8},
            {"nombre": "Diseño y Desarrollo del Producto", "creditos": 8},
            {"nombre": "Envase y Embalaje", "creditos": 8},
            {"nombre": "Ingeniería Financiera", "creditos": 8},
            {"nombre": "Kaizen (Mejora continua)", "creditos": 8},
            {"nombre": "Logística Industrial", "creditos": 8},
            {"nombre": "Sistemas de Producción Avanzados", "creditos": 8},
            {"nombre": "Instrumentación y Control", "creditos": 8}
        ]
    },

    # Fuente: https://escolar1.unam.mx/planes/fes_cuautli/Inform-Cuau.pdf (actualizado 28/sep/2012).
    # 5to, 6to y 7mo semestre eligen 1 optativa cada uno de la misma lista compartida;
    # 8vo y 9no eligen 3 "optativas de elección" cada uno de otra lista compartida.
    "INFORMATICA": {
        "1er Semestre": [
            {"nombre": "Administración I. Proceso Administrativo", "creditos": 6},
            {"nombre": "Comunicación Oral y Escrita", "creditos": 6},
            {"nombre": "Informática I. Introducción a la Informática", "creditos": 12},
            {"nombre": "Programación I. Introducción a la Programación y Ambientes Integrados", "creditos": 8},
            {"nombre": "Taller de Componentes de Hardware", "creditos": 3},
            {"nombre": "Análisis y Diseño de Algoritmos", "creditos": 8},
            {"nombre": "Matemáticas I. Matemáticas Básicas", "creditos": 8}
        ],
        "2do Semestre": [
            {"nombre": "Contabilidad", "creditos": 8},
            {"nombre": "Administración II. Estructuras Administrativas", "creditos": 6},
            {"nombre": "Informática II. Organización de Archivos y Estructura de Datos", "creditos": 12},
            {"nombre": "Programación II. Programación Avanzada", "creditos": 8},
            {"nombre": "Arquitectura de Computadoras", "creditos": 8},
            {"nombre": "Matemáticas II. Lógica Matemática", "creditos": 8}
        ],
        "3er Semestre": [
            {"nombre": "Derecho Informático", "creditos": 8},
            {"nombre": "Metodología de la Investigación", "creditos": 8},
            {"nombre": "Informática III. Análisis y Diseño de Sistemas I", "creditos": 12},
            {"nombre": "Programación III. Programación Visual", "creditos": 8},
            {"nombre": "Sistemas Operativos", "creditos": 8},
            {"nombre": "Matemáticas III. Matemáticas Financieras", "creditos": 8}
        ],
        "4to Semestre": [
            {"nombre": "Contabilidad de Costos", "creditos": 8},
            {"nombre": "Mercadotecnia", "creditos": 6},
            {"nombre": "Informática IV. Análisis y Diseño de Sistemas II", "creditos": 12},
            {"nombre": "Programación IV. Programación de Interfaces", "creditos": 12},
            {"nombre": "Redes de Computadoras I", "creditos": 8},
            {"nombre": "Matemáticas IV. Matemáticas Computacionales", "creditos": 8}
        ],
        "5to Semestre": [
            {"nombre": "Finanzas", "creditos": 8},
            {"nombre": "Administración de Centros de Cómputo", "creditos": 8},
            {"nombre": "Informática V. Industria del Software", "creditos": 12},
            {"nombre": "Introducción a las Bases de Datos", "creditos": 10},
            {"nombre": "Matemáticas V. Estadística", "creditos": 10}
        ],
        "6to Semestre": [
            {"nombre": "Evaluación de Proyectos", "creditos": 8},
            {"nombre": "Economía", "creditos": 8},
            {"nombre": "Informática VI. Tópicos Selectos de Informática", "creditos": 12},
            {"nombre": "Desarrollo de Aplicaciones de Base de Datos", "creditos": 10},
            {"nombre": "Redes de Computadoras II", "creditos": 8}
        ],
        "7mo Semestre": [
            {"nombre": "Análisis y Toma de Decisiones", "creditos": 6},
            {"nombre": "Seminario de Investigación", "creditos": 8},
            {"nombre": "Seguridad Informática", "creditos": 8},
            {"nombre": "Laboratorio de Sistemas de Información", "creditos": 8},
            {"nombre": "Matemáticas VI. Investigación de Operaciones", "creditos": 8}
        ],
        "8vo Semestre": [
            {"nombre": "Auditoría en Informática", "creditos": 8},
            {"nombre": "Ética y Desarrollo Profesional", "creditos": 6}
        ],
        "9no Semestre": [
            {"nombre": "Administración Pública y Política Informática", "creditos": 6}
        ],
        "Optativas (5to, 6to y 7mo Semestre)": [
            {"nombre": "Seminario de Multimedia I", "creditos": 8},
            {"nombre": "Seminario de Proceso Distribuido I", "creditos": 8},
            {"nombre": "Seminario de Sistemas Operativos para Redes I", "creditos": 8},
            {"nombre": "Seminario de Normas y Estándares I", "creditos": 8},
            {"nombre": "Seminario de Administración de Recursos Humanos en Informática I", "creditos": 8},
            {"nombre": "Seminario de Programación en Internet I", "creditos": 8},
            {"nombre": "Seminario de Multimedia II", "creditos": 8},
            {"nombre": "Seminario de Proceso Distribuido II", "creditos": 8},
            {"nombre": "Seminario de Sistemas Operativos para Redes II", "creditos": 8},
            {"nombre": "Seminario de Comercio Electrónico II", "creditos": 8},
            {"nombre": "Seminario de Normas y Estándares II", "creditos": 8},
            {"nombre": "Seminario de Administración de Recursos Humanos en Informática II", "creditos": 8},
            {"nombre": "Seminario de Programación en Internet II", "creditos": 8},
            {"nombre": "Seminario de Inteligencia Artificial II", "creditos": 8},
            {"nombre": "Administración Internacional Comparada", "creditos": 6},
            {"nombre": "Análisis Financieros Matemáticos con Sistemas Electrónicos", "creditos": 8},
            {"nombre": "Análisis Matemáticos Aplicados a la Administración", "creditos": 8},
            {"nombre": "Comercio Exterior I", "creditos": 8},
            {"nombre": "Contabilidades Especiales", "creditos": 8},
            {"nombre": "Habilidades de Liderazgo Estratégico", "creditos": 8},
            {"nombre": "Herramientas de Cómputo Avanzado", "creditos": 8},
            {"nombre": "Inglés I", "creditos": 8},
            {"nombre": "Inglés II", "creditos": 8},
            {"nombre": "Inteligencia de Negocios", "creditos": 6},
            {"nombre": "Seminario de Titulación", "creditos": 0},
            {"nombre": "Simulación de Negocios", "creditos": 8},
            {"nombre": "Sistemas Informáticos Aplicados a la Producción", "creditos": 6}
        ],
        "Optativas de Elección (8vo y 9no Semestre)": [
            {"nombre": "Seminario de Desarrollo de Aplicaciones Web I", "creditos": 8},
            {"nombre": "Seminario de Desarrollo de Aplicaciones Web II", "creditos": 8},
            {"nombre": "Seminario de Administración de Servicios de TI", "creditos": 8},
            {"nombre": "Seminario de Análisis y Extracción de Conocimientos de Base de Datos", "creditos": 8},
            {"nombre": "Seminario de Base de Datos Avanzadas", "creditos": 8},
            {"nombre": "Seminario de Desarrollo de Aplicaciones para Dispositivos Móviles", "creditos": 8},
            {"nombre": "Seminario de Ecuaciones Diferenciales I", "creditos": 8},
            {"nombre": "Seminario de Ecuaciones Diferenciales II", "creditos": 8},
            {"nombre": "Seminario de Inferencia Estadística con uso de Software", "creditos": 8},
            {"nombre": "Seminario de Minería de Datos", "creditos": 8},
            {"nombre": "Seminario de Sistemas Informáticos para la Inteligencia de Negocios", "creditos": 8},
            {"nombre": "Seminario de Técnicas Estadísticas Avanzadas para la Toma de Decisiones I", "creditos": 8},
            {"nombre": "Seminario de Técnicas Estadísticas Avanzadas para la Toma de Decisiones II", "creditos": 8},
            {"nombre": "Seminario de Comercio Electrónico", "creditos": 8},
            {"nombre": "Seminario de Graficación por Computadora", "creditos": 8},
            {"nombre": "Seminario de Graficación por Computadora II", "creditos": 8},
            {"nombre": "Seminario de Inteligencia Artificial I", "creditos": 8},
            {"nombre": "Seminario de Inteligencia Artificial II", "creditos": 8},
            {"nombre": "Seminario de Redes de Computadoras I", "creditos": 8},
            {"nombre": "Seminario de Redes de Computadoras II", "creditos": 8},
            {"nombre": "Seminario de Sistemas Expertos I", "creditos": 8},
            {"nombre": "Seminario de Sistemas Expertos II", "creditos": 8}
        ]
    },

    # Fuentes: https://escolar1.unam.mx/planes/fes_cuautli/Ing-agricola_cuautitlan.pdf
    # y https://oferta.unam.mx/planestudios/ingagri-cuautitlan-planestudios13.pdf
    # (desglosa Orientaciones y Paquetes Terminales). Es la carrera más compleja de
    # las 9: del 7mo al 10mo semestre el alumno combina 1 de 3 Orientaciones + 1 de
    # 4 Paquetes Terminales (elecciones independientes entre sí, no moduladas por el
    # sistema — se listan todas como disponibles). El "Área Libre" (3er y 5to
    # semestre) son materias de otras carreras de la FESC, incluidas tal cual las
    # da el documento fuente.
    "AGRICOLA": {
        "1er Semestre": [
            {"nombre": "Matemáticas I", "creditos": 9},
            {"nombre": "Física I", "creditos": 8},
            {"nombre": "Introducción a la Agricultura", "creditos": 10},
            {"nombre": "Agrometeorología", "creditos": 8},
            {"nombre": "Anatomía y Organografía Vegetal", "creditos": 8},
            {"nombre": "Química I", "creditos": 4},
            {"nombre": "Metodología de la Investigación", "creditos": 6},
            {"nombre": "Cómputo I", "creditos": 4}
        ],
        "2do Semestre": [
            {"nombre": "Matemáticas II", "creditos": 9},
            {"nombre": "Física II", "creditos": 8},
            {"nombre": "Botánica Económica y Sistemática", "creditos": 8},
            {"nombre": "Seminario de Práctica de Campo I", "creditos": 2},
            {"nombre": "Química II", "creditos": 10},
            {"nombre": "Cómputo II", "creditos": 4},
            {"nombre": "Antropología Social", "creditos": 6}
        ],
        "3er Semestre": [
            {"nombre": "Matemáticas III", "creditos": 9},
            {"nombre": "Bioquímica", "creditos": 8},
            {"nombre": "Maquinaria Agrícola I", "creditos": 9},
            {"nombre": "Administración Agropecuaria", "creditos": 6},
            {"nombre": "Práctica de Campo I", "creditos": 2}
        ],
        "4to Semestre": [
            {"nombre": "Diseños Experimentales Agrícolas", "creditos": 6},
            {"nombre": "Edafología", "creditos": 10},
            {"nombre": "Agroecología", "creditos": 8},
            {"nombre": "Fisiología Vegetal", "creditos": 8},
            {"nombre": "Genética", "creditos": 6},
            {"nombre": "Seminario de Práctica de Campo II", "creditos": 2},
            {"nombre": "Economía General", "creditos": 6}
        ],
        "5to Semestre": [
            {"nombre": "Técnicas de Mejoramiento Genético", "creditos": 6},
            {"nombre": "Hidráulica", "creditos": 8},
            {"nombre": "Topografía", "creditos": 9},
            {"nombre": "Maquinaria Agrícola II", "creditos": 9},
            {"nombre": "Entomología", "creditos": 9},
            {"nombre": "Práctica de Campo II", "creditos": 2},
            {"nombre": "Economía Agrícola", "creditos": 6}
        ],
        "6to Semestre": [
            {"nombre": "Uso y Manejo del Agua", "creditos": 8},
            {"nombre": "Fertilidad y Manejo de Suelos", "creditos": 8},
            {"nombre": "Dasonomía", "creditos": 8},
            {"nombre": "Fitopatología", "creditos": 9},
            {"nombre": "Control de la Maleza", "creditos": 9},
            {"nombre": "Seminario de Práctica de Campo III", "creditos": 2},
            {"nombre": "Derecho Agrario", "creditos": 6},
            {"nombre": "Percepción Remota Aplicada a la Agricultura", "creditos": 4}
        ],
        "7mo Semestre": [
            {"nombre": "Producción de Granos y Oleaginosas", "creditos": 9},
            {"nombre": "Producción de Hortalizas", "creditos": 9},
            {"nombre": "Práctica de Campo III", "creditos": 2}
        ],
        "8vo Semestre": [
            {"nombre": "Producción de Forrajes y Manejo de Pastizales", "creditos": 9},
            {"nombre": "Producción de Frutales", "creditos": 9},
            {"nombre": "Financiamiento Agropecuario", "creditos": 6}
        ],
        "9no Semestre": [
            {"nombre": "Formulación y Evaluación de Proyectos", "creditos": 6},
            {"nombre": "Práctica de Campo IV", "creditos": 2}
        ],
        "10mo Semestre": [
            {"nombre": "Comercialización de Productos Agrícolas", "creditos": 8},
            {"nombre": "Seminario de Tesis", "creditos": 6},
            {"nombre": "Práctica de Campo V", "creditos": 2}
        ],
        "Orientación: Agroecosistemas": [
            {"nombre": "Fisiotecnia", "creditos": 8},
            {"nombre": "Agricultura en Zonas Templadas", "creditos": 8},
            {"nombre": "Agricultura en Zonas Áridas", "creditos": 8},
            {"nombre": "Agricultura en Zonas Tropicales y Subtropicales", "creditos": 8},
            {"nombre": "Sistemas de Producción Forzada", "creditos": 8},
            {"nombre": "Impacto Ambiental", "creditos": 6},
            {"nombre": "Análisis de Sistemas Agrícolas", "creditos": 6}
        ],
        "Orientación: Tecnología Agrícola": [
            {"nombre": "Mecánica", "creditos": 8},
            {"nombre": "Manejo Poscosecha", "creditos": 8},
            {"nombre": "Mecanización Agrícola", "creditos": 10},
            {"nombre": "Dibujo", "creditos": 6},
            {"nombre": "Máquinas y Mecanismos", "creditos": 8},
            {"nombre": "Operación de Obras Hidráulicas", "creditos": 6},
            {"nombre": "Diseño", "creditos": 6}
        ],
        "Orientación: Desarrollo Rural": [
            {"nombre": "Organización Agraria", "creditos": 8},
            {"nombre": "Inferencia Estadística", "creditos": 8},
            {"nombre": "Planeación Agropecuaria", "creditos": 8},
            {"nombre": "Ingeniería Económica", "creditos": 6},
            {"nombre": "Desarrollo Rural", "creditos": 6},
            {"nombre": "Geografía Económica", "creditos": 8},
            {"nombre": "Planeación Estratégica", "creditos": 8}
        ],
        "Paquete Terminal: Producción": [
            {"nombre": "Propagación de Plantas", "creditos": 6},
            {"nombre": "Horticultura Avanzada", "creditos": 8},
            {"nombre": "Fruticultura Avanzada", "creditos": 8},
            {"nombre": "Producción y Tecnología de Semillas", "creditos": 8}
        ],
        "Paquete Terminal: Biotecnología": [
            {"nombre": "Cultivo de Tejidos Vegetales", "creditos": 8},
            {"nombre": "Micropropagación", "creditos": 8},
            {"nombre": "Biología Molecular", "creditos": 8},
            {"nombre": "Transformación Génica de Plantas", "creditos": 6}
        ],
        "Paquete Terminal: Cultivos Forzados": [
            {"nombre": "Plasticultura", "creditos": 6},
            {"nombre": "Tecnología en Sistemas Forzados", "creditos": 8},
            {"nombre": "Invernaderos", "creditos": 8},
            {"nombre": "Arboricultura", "creditos": 8}
        ],
        "Paquete Terminal: Transferencia de Tecnología": [
            {"nombre": "Procesos de la Comunicación", "creditos": 8},
            {"nombre": "Teorías del Desarrollo", "creditos": 8},
            {"nombre": "Promoción Agrícola", "creditos": 6},
            {"nombre": "Innovación y Desarrollo Tecnológico", "creditos": 8}
        ],
        "Área Libre (3er y 5to Semestre)": [
            {"nombre": "Introducción a la Informática (Área Libre)", "creditos": 8},
            {"nombre": "Análisis y Diseño de Estructuras Administrativas (Área Libre)", "creditos": 8},
            {"nombre": "Sistemas de Información (Área Libre)", "creditos": 8},
            {"nombre": "Problemas Económicos de México (Área Libre)", "creditos": 8},
            {"nombre": "Análisis y Diseño de Procedimientos Administrativos (Área Libre)", "creditos": 8},
            {"nombre": "Economía y la Empresa (Área Libre)", "creditos": 8},
            {"nombre": "Comportamiento Humano de las Organizaciones (Área Libre)", "creditos": 8},
            {"nombre": "Comunicación Oral y Escrita (Área Libre)", "creditos": 6},
            {"nombre": "Electricidad y Magnetismo (Área Libre)", "creditos": 11},
            {"nombre": "Introducción a la Tecnología de Materiales (Área Libre)", "creditos": 10},
            {"nombre": "Termofluidos (Área Libre)", "creditos": 10},
            {"nombre": "Recursos y Necesidades de México (Área Libre)", "creditos": 6},
            {"nombre": "Gestión de Empresas (Área Libre)", "creditos": 8},
            {"nombre": "Planeación (Área Libre)", "creditos": 8},
            {"nombre": "Diseño de Equipo (Área Libre)", "creditos": 6},
            {"nombre": "Relaciones Humanas (Área Libre)", "creditos": 6},
            {"nombre": "Bromatología (Área Libre)", "creditos": 12},
            {"nombre": "Apicultura (Área Libre)", "creditos": 4},
            {"nombre": "Exterior y Manejo de los Animales (Área Libre)", "creditos": 5},
            {"nombre": "Zootecnia General (Área Libre)", "creditos": 8},
            {"nombre": "Relaciones Laborales (Área Libre)", "creditos": 8},
            {"nombre": "Dirección de Empresas (Área Libre)", "creditos": 6},
            {"nombre": "Tecnología de Materiales (Área Libre)", "creditos": 6},
            {"nombre": "Química Ambiental I (Área Libre)", "creditos": 6},
            {"nombre": "Planeación y Desarrollo Industrial (Área Libre)", "creditos": 6},
            {"nombre": "Seguridad e Higiene Industrial (Área Libre)", "creditos": 6},
            {"nombre": "Tratamiento de Aguas (Área Libre)", "creditos": 8},
            {"nombre": "Desarrollo de la Personalidad Profesional (Área Libre)", "creditos": 7},
            {"nombre": "Administración y Estrategias de Producción (Área Libre)", "creditos": 7},
            {"nombre": "Administración por Objetivos (Área Libre)", "creditos": 7},
            {"nombre": "Contaminación de Suelos (Área Libre)", "creditos": 7},
            {"nombre": "Temas Selectos de los Problemas de la Civilización Contemporánea (Área Libre)", "creditos": 8},
            {"nombre": "Teoría de la Dialéctica y la Retórica (Área Libre)", "creditos": 2}
        ]
    },

    # Fuente: https://escolar1.unam.mx/planes/fes_cuautli/MVZ-Cuau.pdf (aprobado 10/dic/2007).
    # Tiene dos bancos de optativas compartidos entre varios semestres ("Básicas" en
    # 2do/4to/6to y "de Profundización" en 6to a 10mo), más dos bolsas de 9no y 10mo
    # semestre donde se eligen 5 de 9 y 5 de 8 materias respectivamente.
    "MVZ": {
        "1er Semestre": [
            {"nombre": "Anatomía Veterinaria Básica", "creditos": 12},
            {"nombre": "Bioestadística", "creditos": 6},
            {"nombre": "Bioquímica", "creditos": 13},
            {"nombre": "Exterior y Manejo de los Animales", "creditos": 5},
            {"nombre": "Fisicoquímica Fisiológica", "creditos": 4}
        ],
        "2do Semestre": [
            {"nombre": "Alimentos y Forrajes", "creditos": 10},
            {"nombre": "Biología Celular", "creditos": 8},
            {"nombre": "Etología", "creditos": 5},
            {"nombre": "Introducción a la Zootecnia", "creditos": 8},
            {"nombre": "Fisiología General", "creditos": 10}
        ],
        "3er Semestre": [
            {"nombre": "Bacteriología y Micología", "creditos": 14},
            {"nombre": "Biología del Desarrollo e Histología Veterinaria", "creditos": 14},
            {"nombre": "Ética de la Práctica Profesional del MVZ", "creditos": 4},
            {"nombre": "Fisiología Veterinaria", "creditos": 16}
        ],
        "4to Semestre": [
            {"nombre": "Economía Zootécnica", "creditos": 7},
            {"nombre": "Genética", "creditos": 12},
            {"nombre": "Nutrición Animal", "creditos": 6},
            {"nombre": "Parasitología", "creditos": 10},
            {"nombre": "Virología", "creditos": 6}
        ],
        "5to Semestre": [
            {"nombre": "Alimentación Animal", "creditos": 6},
            {"nombre": "Anatomía Veterinaria Aplicada", "creditos": 10},
            {"nombre": "Bienestar Animal", "creditos": 6},
            {"nombre": "Inmunología", "creditos": 8},
            {"nombre": "Inocuidad de los Alimentos de Origen Pecuario", "creditos": 8}
        ],
        "6to Semestre": [
            {"nombre": "Patología General", "creditos": 12},
            {"nombre": "Epidemiología", "creditos": 6},
            {"nombre": "Propedéutica Clínica Veterinaria", "creditos": 6},
            {"nombre": "Taller de Control de Calidad de Alimentos de Origen Pecuario", "creditos": 4}
        ],
        "7mo Semestre": [
            {"nombre": "Salubridad Pública Veterinaria", "creditos": 8},
            {"nombre": "Patología Sistémica", "creditos": 16},
            {"nombre": "Farmacología, Toxicología y Terapéutica Médico Veterinaria", "creditos": 16}
        ],
        "8vo Semestre": [
            {"nombre": "Reproducción Animal", "creditos": 10},
            {"nombre": "Enfermedades Infecciosas I", "creditos": 10},
            {"nombre": "Patología Clínica", "creditos": 8},
            {"nombre": "Técnica Quirúrgica", "creditos": 6}
        ],
        "9no Semestre - Zootécnicas (elegir 5 de 9)": [
            {"nombre": "Fauna Silvestre I", "creditos": 5},
            {"nombre": "Zootecnia Caprina", "creditos": 5},
            {"nombre": "Zootecnia Canina y Felina", "creditos": 5},
            {"nombre": "Zootecnia de Bovinos Productores de Carne", "creditos": 5},
            {"nombre": "Zootecnia Bovinos Productores de Leche", "creditos": 5},
            {"nombre": "Zootecnia de las Aves", "creditos": 5},
            {"nombre": "Zootecnia Equina", "creditos": 5},
            {"nombre": "Zootecnia Ovina", "creditos": 5},
            {"nombre": "Zootecnia Porcina", "creditos": 5}
        ],
        "10mo Semestre - Clínicas (elegir 5 de 8)": [
            {"nombre": "Clínica Bovina", "creditos": 5},
            {"nombre": "Clínica Canina y Felina", "creditos": 5},
            {"nombre": "Clínica Caprina", "creditos": 5},
            {"nombre": "Clínica de Aves", "creditos": 5},
            {"nombre": "Clínica Equina", "creditos": 5},
            {"nombre": "Clínica Ovina", "creditos": 5},
            {"nombre": "Clínica Porcina", "creditos": 5},
            {"nombre": "Fauna Silvestre II", "creditos": 5}
        ],
        "Optativas de Elección Básicas (2do, 4to y 6to Semestre)": [
            {"nombre": "Administración Pública Veterinaria", "creditos": 4},
            {"nombre": "Comprensión de Lectura en Lengua Inglesa", "creditos": 8},
            {"nombre": "Comprensión de Lectura en Lengua Francesa", "creditos": 8},
            {"nombre": "Desarrollo Sustentable", "creditos": 4},
            {"nombre": "Estadística No Paramétrica", "creditos": 4},
            {"nombre": "Geografía Económica", "creditos": 4},
            {"nombre": "Introducción al Diseño Experimental", "creditos": 4},
            {"nombre": "Legislación Veterinaria", "creditos": 4},
            {"nombre": "Metodología de la Investigación Científica", "creditos": 4},
            {"nombre": "Peritaje Zootécnico", "creditos": 4},
            {"nombre": "Razas de Perros y Gatos", "creditos": 4},
            {"nombre": "Sociología Rural y Urbana", "creditos": 4}
        ],
        "Optativas de Elección de Profundización (6to a 10mo Semestre)": [
            {"nombre": "Administración de Empresas Agropecuarias", "creditos": 6},
            {"nombre": "Análisis de Factibilidad Económica", "creditos": 4},
            {"nombre": "Apicultura", "creditos": 6},
            {"nombre": "Bioinformática para MVZ", "creditos": 6},
            {"nombre": "Cunicultura", "creditos": 6},
            {"nombre": "Enfermedades Infecciosas II", "creditos": 8},
            {"nombre": "Especificación de Productos de Origen Animal", "creditos": 4},
            {"nombre": "Evaluación de los Alimentos de Consumo Animal", "creditos": 4},
            {"nombre": "Formulación y Fabricación de Alimentos Balanceados", "creditos": 4},
            {"nombre": "Genómica Animal", "creditos": 6},
            {"nombre": "Imagenología", "creditos": 6},
            {"nombre": "Laboratorio de Análisis Clínicos", "creditos": 4},
            {"nombre": "Mejoramiento Genético Animal", "creditos": 6},
            {"nombre": "Mercadotecnia para Veterinarios", "creditos": 4},
            {"nombre": "Microorganismos Patógenos de Origen Pecuario", "creditos": 6},
            {"nombre": "Piscicultura", "creditos": 6},
            {"nombre": "Producción de Animales de Laboratorio", "creditos": 6},
            {"nombre": "Seminario de Investigación I", "creditos": 6},
            {"nombre": "Seminario de Investigación II", "creditos": 6},
            {"nombre": "Seminario de Investigación III", "creditos": 6},
            {"nombre": "Seminario de Investigación IV", "creditos": 6},
            {"nombre": "Seminario de Titulación (Medicina Veterinaria)", "creditos": 0},
            {"nombre": "Temas Selectos de Biología Molecular", "creditos": 6},
            {"nombre": "Terapéutica Quirúrgica", "creditos": 4},
            {"nombre": "Tópicos Selectos de Cirugía en Perros y Gatos", "creditos": 4}
        ]
    },
}

# --- BASE DE DATOS ---
def get_db():
    conexion = sqlite3.connect('base_dts.db')
    conexion.row_factory = sqlite3.Row
    return conexion

def _es_hash_valido(password):
    """True si la contraseña ya está hasheada con werkzeug.security (evita rehashear dos veces)."""
    return isinstance(password, str) and password.startswith(('pbkdf2:', 'scrypt:'))

def _migrar_passwords_en_texto_plano(cur, tabla, columna_usuario):
    filas = cur.execute(f"SELECT {columna_usuario}, password FROM {tabla}").fetchall()
    for usuario, password in filas:
        if not _es_hash_valido(password):
            cur.execute(f"UPDATE {tabla} SET password=? WHERE {columna_usuario}=?",
                        (generate_password_hash(password), usuario))

def _asegurar_columna(cur, tabla, columna, definicion):
    """Agrega una columna a una tabla ya existente si todavía no la tiene (migración idempotente)."""
    columnas = [fila[1] for fila in cur.execute(f"PRAGMA table_info({tabla})").fetchall()]
    if columna not in columnas:
        cur.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion}")

def _eliminar_columna(cur, tabla, columna):
    """Quita una columna de una tabla ya existente si todavía la tiene (migración idempotente)."""
    columnas = [fila[1] for fila in cur.execute(f"PRAGMA table_info({tabla})").fetchall()]
    if columna in columnas:
        cur.execute(f"ALTER TABLE {tabla} DROP COLUMN {columna}")

def _migrar_carrera_profesor_a_tabla_relacion(cur):
    """Copia el valor único de profesores.carrera (si existe) a profesor_carreras
    antes de eliminar esa columna, para no perder altas anteriores a un solo valor."""
    columnas = [fila[1] for fila in cur.execute("PRAGMA table_info(profesores)").fetchall()]
    if "carrera" not in columnas:
        return
    filas = cur.execute("SELECT usuario, carrera FROM profesores WHERE carrera IS NOT NULL").fetchall()
    for usuario, carrera in filas:
        cur.execute("INSERT OR IGNORE INTO profesor_carreras (usuario, carrera) VALUES (?,?)", (usuario, carrera))

def init_db():
    con = get_db()
    cur = con.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS alumnos
                    (cuenta TEXT PRIMARY KEY, password TEXT, nombre TEXT,
                     password_temporal INTEGER DEFAULT 0, carrera TEXT DEFAULT 'ITSE',
                     fecha_nacimiento TEXT)''')
    cur.execute('''CREATE TABLE IF NOT EXISTS profesores
                    (usuario TEXT PRIMARY KEY, password TEXT, nombre TEXT,
                     password_temporal INTEGER DEFAULT 0, fecha_nacimiento TEXT)''')
    cur.execute('''CREATE TABLE IF NOT EXISTS administradores
                    (usuario TEXT PRIMARY KEY, password TEXT, nombre TEXT)''')
    _asegurar_columna(cur, "alumnos", "password_temporal", "INTEGER DEFAULT 0")
    _asegurar_columna(cur, "alumnos", "carrera", "TEXT DEFAULT 'ITSE'")
    _asegurar_columna(cur, "alumnos", "fecha_nacimiento", "TEXT")
    _eliminar_columna(cur, "alumnos", "semestre")
    _asegurar_columna(cur, "profesores", "password_temporal", "INTEGER DEFAULT 0")
    _asegurar_columna(cur, "profesores", "fecha_nacimiento", "TEXT")
    cur.execute('''CREATE TABLE IF NOT EXISTS evaluaciones
                    (cuenta TEXT, materia TEXT, estilo TEXT, recomendacion TEXT,
                     PRIMARY KEY (cuenta, materia))''')
    cur.execute('''CREATE TABLE IF NOT EXISTS inscripciones
                    (cuenta TEXT, materia TEXT,
                     PRIMARY KEY (cuenta, materia))''')
    cur.execute('''CREATE TABLE IF NOT EXISTS profesor_carreras
                    (usuario TEXT, carrera TEXT,
                     PRIMARY KEY (usuario, carrera))''')
    _migrar_carrera_profesor_a_tabla_relacion(cur)
    _eliminar_columna(cur, "profesores", "carrera")
    cur.execute('''CREATE TABLE IF NOT EXISTS correcciones_profesor
                    (cuenta TEXT, materia TEXT, recomendacion_corregida TEXT,
                     profesor TEXT, fecha TEXT,
                     PRIMARY KEY (cuenta, materia))''')

    # Migrar datos iniciales si las tablas están vacías
    if not cur.execute("SELECT 1 FROM alumnos LIMIT 1").fetchone():
        for cuenta, d in BASE_DE_DATOS.items():
            cur.execute("INSERT INTO alumnos (cuenta, password, nombre, carrera) VALUES (?,?,?,?)",
                        (cuenta, generate_password_hash(d["password"]), d["nombre"], d.get("carrera", "ITSE")))
    if not cur.execute("SELECT 1 FROM administradores LIMIT 1").fetchone():
        cur.execute("INSERT INTO administradores VALUES (?,?,?)", ("admin", generate_password_hash("admin"), "Administración FESC"))

    # Migrar a hash cualquier contraseña en texto plano que ya existiera (bases de datos previas a este cambio)
    _migrar_passwords_en_texto_plano(cur, "alumnos", "cuenta")
    _migrar_passwords_en_texto_plano(cur, "profesores", "usuario")
    _migrar_passwords_en_texto_plano(cur, "administradores", "usuario")

    cur.execute('''CREATE TABLE IF NOT EXISTS actividades_ia
                    (id INTEGER PRIMARY KEY AUTOINCREMENT,
                     cuenta TEXT, materia TEXT, estilo TEXT,
                     actividad TEXT, actividad_corregida TEXT,
                     profesor_corrector TEXT, fecha_correccion TEXT)''')
    _asegurar_columna(cur, "actividades_ia", "titulo", "TEXT")
    cur.execute('''CREATE TABLE IF NOT EXISTS entregas_actividad_ia
                    (id INTEGER PRIMARY KEY AUTOINCREMENT,
                     actividad_id INTEGER, cuenta TEXT,
                     contenido_texto TEXT, archivo TEXT,
                     fecha_entrega TEXT,
                     calificacion REAL, criterios TEXT, explicacion TEXT,
                     estado TEXT DEFAULT 'pendiente', fecha_calificacion TEXT,
                     FOREIGN KEY(actividad_id) REFERENCES actividades_ia(id))''')
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

def _generar_password_temporal():
    return secrets.token_urlsafe(6)

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

def get_todos_admins():
    con = get_db()
    rows = con.execute("SELECT * FROM administradores").fetchall()
    con.close()
    return {r["usuario"]: dict(r) for r in rows}

def _clave_orden_alfabetico(texto):
    return unicodedata.normalize('NFD', texto).encode('ascii', 'ignore').decode('ascii').lower()

def obtener_materias_inscritas(cuenta):
    conexion = sqlite3.connect('base_dts.db')
    cursor = conexion.cursor()
    cursor.execute("SELECT materia FROM inscripciones WHERE cuenta=? ", (cuenta,))
    filas = cursor.fetchall()
    conexion.close()
    return [fila[0] for fila in filas]

def obtener_carreras_profesor(usuario):
    con = get_db()
    filas = con.execute("SELECT carrera FROM profesor_carreras WHERE usuario=?", (usuario,)).fetchall()
    con.close()
    return [f["carrera"] for f in filas]

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
            if alumno and check_password_hash(alumno['password'], password):
                session.permanent = True
                session['usuario'] = cuenta
                if alumno.get('password_temporal'):
                    return redirect(url_for('cambiar_contrasena'))
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
    datos_alumno['carrera_nombre'] = CARRERAS.get(datos_alumno.get('carrera'), datos_alumno.get('carrera') or '—')

    conexion = sqlite3.connect('base_dts.db')
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
    plan_original = PLANES_DE_ESTUDIO.get(datos_alumno.get('carrera'), {})
    plan_alumno = {
        semestre: sorted(lista, key=lambda m: _clave_orden_alfabetico(m['nombre']))
        for semestre, lista in plan_original.items()
    }
    return render_template('materias.html', alumno=datos_alumno, plan=plan_alumno)

@app.route('/guardar_materias', methods=['POST'])
def guardar_materias():
    if 'usuario' not in session: return redirect(url_for('login'))

    cuenta_actual = session['usuario']
    datos_alumno = get_alumno(cuenta_actual)
    if datos_alumno.get('carrera') not in PLANES_DE_ESTUDIO:
        return redirect(url_for('mis_materias'))

    materias_seleccionadas = request.form.getlist('materias_inscritas')

    total_creditos = 0
    for semestre, lista in PLANES_DE_ESTUDIO[datos_alumno['carrera']].items():
        for mat in lista:
            if mat['nombre'] in materias_seleccionadas:
                total_creditos += mat['creditos']

    if total_creditos <= 64:
        conexion = sqlite3.connect('base_dts.db')
        cursor = conexion.cursor()
        materias_previas = {f[0] for f in cursor.execute(
            "SELECT materia FROM inscripciones WHERE cuenta=?", (cuenta_actual,)).fetchall()}
        materias_dadas_de_baja = materias_previas - set(materias_seleccionadas)

        cursor.execute("DELETE FROM inscripciones WHERE cuenta=?", (cuenta_actual,))
        for mat in materias_seleccionadas:
            cursor.execute("INSERT INTO inscripciones (cuenta, materia) VALUES (?, ?)", (cuenta_actual, mat))

        # Al dar de baja una materia, se borran también el consejo y las actividades
        # que la IA generó para ella (y sus entregas/calificaciones), no solo la inscripción.
        for mat in materias_dadas_de_baja:
            cursor.execute("""DELETE FROM entregas_actividad_ia WHERE actividad_id IN
                               (SELECT id FROM actividades_ia WHERE cuenta=? AND materia=?)""",
                           (cuenta_actual, mat))
            cursor.execute("DELETE FROM actividades_ia WHERE cuenta=? AND materia=?", (cuenta_actual, mat))
            cursor.execute("DELETE FROM evaluaciones WHERE cuenta=? AND materia=?", (cuenta_actual, mat))
            cursor.execute("DELETE FROM correcciones_profesor WHERE cuenta=? AND materia=?", (cuenta_actual, mat))

        conexion.commit()
        conexion.close()

    return redirect(url_for('mis_materias'))

@app.route('/mis_materias')
def mis_materias():
    if 'usuario' not in session: return redirect(url_for('login'))
    cuenta_actual = session['usuario']
    datos_alumno = get_alumno(cuenta_actual)
    datos_alumno['materias'] = obtener_materias_inscritas(cuenta_actual)

    conexion = sqlite3.connect('base_dts.db')
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

@app.route('/recuperar_contrasena', methods=['GET', 'POST'])
def recuperar_contrasena():
    mensaje = None
    error = None
    if request.method == 'POST':
        cuenta = request.form.get('cuenta', '').strip()
        alumno = get_alumno(cuenta)
        if alumno:
            nueva_temporal = _generar_password_temporal()
            con = get_db()
            con.execute("UPDATE alumnos SET password=?, password_temporal=1 WHERE cuenta=?",
                        (generate_password_hash(nueva_temporal), cuenta))
            con.commit()
            con.close()
            mensaje = f"Tu nueva contraseña temporal es: {nueva_temporal}. Al iniciar sesión con ella te pediremos que la cambies por una de tu elección."
        else:
            error = "No se encontró ningún alumno con ese número de cuenta."
    return render_template('recuperar_contrasena.html', mensaje=mensaje, error=error)

@app.route('/cambiar_contrasena', methods=['GET', 'POST'])
def cambiar_contrasena():
    if 'usuario' not in session: return redirect(url_for('login'))
    cuenta_actual = session['usuario']
    alumno = get_alumno(cuenta_actual)
    error = None
    if request.method == 'POST':
        password_actual = request.form.get('password_actual', '')
        password_nueva = request.form.get('password_nueva', '')
        password_confirmar = request.form.get('password_confirmar', '')
        if not check_password_hash(alumno['password'], password_actual):
            error = "Tu contraseña actual no es correcta."
        elif len(password_nueva) < 6:
            error = "La nueva contraseña debe tener al menos 6 caracteres."
        elif password_nueva != password_confirmar:
            error = "La confirmación no coincide con la nueva contraseña."
        else:
            con = get_db()
            con.execute("UPDATE alumnos SET password=?, password_temporal=0 WHERE cuenta=?",
                        (generate_password_hash(password_nueva), cuenta_actual))
            con.commit()
            con.close()
            return redirect(url_for('inicio'))
    return render_template('cambiar_contrasena.html', error=error,
                            era_temporal=bool(alumno.get('password_temporal')))

@app.route('/test/<nombre_materia>')
def test_materia(nombre_materia):
    if 'usuario' not in session: return redirect(url_for('login'))
    return render_template('index.html', lista_preguntas=mi_evaluador.preguntas, materia=nombre_materia)

ACTIVIDADES_FALLBACK = [
    {"titulo": "Mapas conceptuales", "descripcion": "Organiza los temas de la materia en esquemas visuales que conecten ideas principales y secundarias."},
    {"titulo": "Fichas de repaso", "descripcion": "Resume cada tema en tarjetas breves que puedas revisar antes de un examen."},
    {"titulo": "Práctica guiada", "descripcion": "Resuelve ejercicios del libro paso a paso, verificando cada resultado contra la solución oficial."},
]

_ESQUEMA_ACTIVIDADES_IA = {
    "type": "object",
    "properties": {
        "actividades": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "titulo": {"type": "string"},
                    "descripcion": {"type": "string"},
                },
                "required": ["titulo", "descripcion"],
            },
        },
    },
    "required": ["actividades"],
}

_ESQUEMA_CALIFICACION_IA = {
    "type": "object",
    "properties": {
        "criterios": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "nombre": {"type": "string"},
                    "descripcion": {"type": "string"},
                    "puntaje_maximo": {"type": "number"},
                    "puntaje_obtenido": {"type": "number"},
                },
                "required": ["nombre", "descripcion", "puntaje_maximo", "puntaje_obtenido"],
            },
        },
        "calificacion_total": {"type": "number"},
        "explicacion": {"type": "string"},
    },
    "required": ["criterios", "calificacion_total", "explicacion"],
}

_MIMETYPES_SOPORTADOS_IA = {
    "pdf": "application/pdf", "png": "image/png",
    "jpg": "image/jpeg", "jpeg": "image/jpeg", "txt": "text/plain",
}

def _generar_actividades_ia(estilo_ganador, materia_evaluada):
    prompt = (
        f"Actúa como un asesor académico universitario de la FES Cuautitlán, UNAM. Redacta en tono formal, "
        f"profesional y directo, sin exclamaciones, sin apodos hacia el alumno (nada de 'joven' u otras "
        f"muletillas) y sin ningún texto introductorio ni de cierre. Para un alumno con estilo de aprendizaje "
        f"{estilo_ganador} en la materia '{materia_evaluada}', genera exactamente 3 actividades de estudio "
        f"prácticas y concretas, cada una con un título corto y una descripción breve. No uses asteriscos ni "
        f"saludos ni despedidas."
    )
    try:
        respuesta = cliente_ia.models.generate_content(
            model='gemini-2.5-flash', contents=prompt,
            config=genai_types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_ESQUEMA_ACTIVIDADES_IA,
            ))
        actividades = json.loads(respuesta.text)["actividades"]
        if not actividades:
            return ACTIVIDADES_FALLBACK
        return actividades[:3]
    except Exception:
        return ACTIVIDADES_FALLBACK

def _calificar_actividad_con_ia(materia, estilo, titulo, descripcion, contenido_texto, archivo_path, archivo_ext):
    partes_entrega = []
    if contenido_texto:
        partes_entrega.append(f"Texto entregado por el alumno:\n{contenido_texto}")
    mimetype = _MIMETYPES_SOPORTADOS_IA.get(archivo_ext)
    if archivo_path and mimetype:
        with open(archivo_path, 'rb') as f:
            partes_entrega.append(genai_types.Part.from_bytes(data=f.read(), mime_type=mimetype))
    elif archivo_path:
        partes_entrega.append(f"El alumno adjuntó un archivo ({os.path.basename(archivo_path)}) que no se pudo "
                               f"leer automáticamente; califica solo con base en el texto disponible, si lo hay.")

    prompt = (
        f"Actúa como un evaluador académico universitario de la FES Cuautitlán, UNAM, revisando la entrega de un "
        f"alumno con estilo de aprendizaje {estilo} para la materia '{materia}'.\n"
        f"Actividad asignada — {titulo}: {descripcion}\n\n"
        f"Define entre 3 y 5 criterios de evaluación pertinentes para esta actividad en concreto (nombre corto, "
        f"descripción breve de qué evalúa cada uno, y un puntaje máximo por criterio; la suma de los puntajes "
        f"máximos debe ser 100). Califica la entrega del alumno contra cada criterio con un puntaje obtenido "
        f"(nunca mayor al máximo de ese criterio), calcula la calificación total como la suma de los puntajes "
        f"obtenidos, y escribe una explicación clara y concreta — entendible tanto por el alumno como por su "
        f"profesor — de en qué te basaste para calificar así, qué se hizo bien y qué falta. Tono profesional y "
        f"directo, sin saludos ni despedidas, sin asteriscos."
    )
    try:
        respuesta = cliente_ia.models.generate_content(
            model='gemini-2.5-flash', contents=[prompt, *partes_entrega],
            config=genai_types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_ESQUEMA_CALIFICACION_IA,
            ))
        return json.loads(respuesta.text)
    except Exception:
        return None

@app.route('/evaluar', methods=['POST'])
def evaluar():
    if 'usuario' not in session: return redirect(url_for('login'))
    if request.method == 'POST':
        materia_evaluada = request.form.get('materia_oculta')
        respuestas_usuario = [request.form.get(f'p{i}') for i in range(len(mi_evaluador.preguntas))]
        resultados = mi_evaluador.evaluar_desde_web(respuestas_usuario)
        estilo_ganador = resultados['estilo_ganador']['nombre']
        cuenta_actual = session['usuario']
        
        prompt = f"Actúa como un asesor académico universitario de la FES Cuautitlán, UNAM. Redacta en un tono profesional, claro y cordial, como el de un asesor académico real explicándole algo a un alumno: evita los dos extremos, ni teatral ni con apodos como 'joven', pero tampoco telegráfico o de una sola frase suelta. Cada punto debe incluir una breve explicación (1-2 oraciones) de por qué es útil para ese estilo de aprendizaje. No incluyas saludo, presentación ni despedida: tu respuesta debe iniciar directamente en '1. Consejo:'. Para un alumno que aprende de forma {estilo_ganador} en la materia '{materia_evaluada}', responde exactamente con este formato, conservando las etiquetas:\n1. Consejo: [tip explicado en 1-2 oraciones]\n2. Libro: [título y autor, con una breve razón de por qué ayuda]\n3. Recurso: [canal o sitio, con una breve razón de por qué ayuda]\nNo uses asteriscos."
        try:
            respuesta_ia = cliente_ia.models.generate_content(model='gemini-2.5-flash', contents=prompt)
            consejo_generado = respuesta_ia.text
        except Exception:
            consejo_generado = "1. Consejo: Haz mapas mentales.\n2. Libro: Consulta la bibliografía oficial.\n3. Recurso: Busca tutoriales en YouTube."
        
        # Generar actividades IA (cada una queda como su propia fila, con su propio título)
        actividades_generadas = _generar_actividades_ia(estilo_ganador, materia_evaluada)

        conexion = sqlite3.connect('base_dts.db')
        cursor = conexion.cursor()
        cursor.execute("REPLACE INTO evaluaciones (cuenta, materia, estilo, recomendacion) VALUES (?, ?, ?, ?)",
                       (cuenta_actual, materia_evaluada, estilo_ganador, consejo_generado))
        # Guardar actividades IA (reemplazar si ya existían, junto con entregas/calificaciones previas)
        cursor.execute("""DELETE FROM entregas_actividad_ia WHERE actividad_id IN
                           (SELECT id FROM actividades_ia WHERE cuenta=? AND materia=?)""",
                       (cuenta_actual, materia_evaluada))
        cursor.execute("DELETE FROM actividades_ia WHERE cuenta=? AND materia=?", (cuenta_actual, materia_evaluada))
        for act in actividades_generadas:
            cursor.execute("INSERT INTO actividades_ia (cuenta, materia, estilo, titulo, actividad) VALUES (?,?,?,?,?)",
                           (cuenta_actual, materia_evaluada, estilo_ganador, act["titulo"], act["descripcion"]))
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
        "SELECT id, materia, estilo, titulo, actividad, actividad_corregida FROM actividades_ia WHERE cuenta=? ORDER BY materia, id",
        (cuenta_actual,)).fetchall()
    tareas = con.execute(
        "SELECT id, materia, titulo, descripcion, fecha_entrega, archivo, profesor, fecha_asignacion FROM tareas_profesor WHERE cuenta=? ORDER BY fecha_entrega",
        (cuenta_actual,)).fetchall()
    # Obtener entregas del alumno
    entregas = {row['tarea_id']: dict(row) for row in con.execute(
        "SELECT * FROM entregas_tarea WHERE cuenta=?", (cuenta_actual,)).fetchall()}
    entregas_actividades = {row['actividad_id']: dict(row) for row in con.execute(
        "SELECT * FROM entregas_actividad_ia WHERE cuenta=?", (cuenta_actual,)).fetchall()}
    for entrega in entregas_actividades.values():
        entrega['criterios'] = json.loads(entrega['criterios']) if entrega['criterios'] else []
    con.close()

    return render_template('mis_actividades.html',
                           alumno=datos_alumno,
                           actividades=[dict(a) for a in actividades],
                           tareas=[dict(t) for t in tareas],
                           entregas=entregas,
                           entregas_actividades=entregas_actividades)

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
            "SELECT id, materia, estilo, titulo, actividad, actividad_corregida, profesor_corrector FROM actividades_ia WHERE cuenta=? ORDER BY materia, id",
            (cuenta,)).fetchall()
        entregas_acts = {row['actividad_id']: dict(row) for row in con.execute(
            "SELECT * FROM entregas_actividad_ia WHERE cuenta=?", (cuenta,)).fetchall()}
        acts_con_entrega = []
        for a in acts:
            act_dict = dict(a)
            entrega = entregas_acts.get(act_dict['id'])
            if entrega:
                entrega['criterios'] = json.loads(entrega['criterios']) if entrega['criterios'] else []
            act_dict['entrega'] = entrega
            acts_con_entrega.append(act_dict)
        actividades[cuenta] = {'nombre': nombre, 'cuenta': cuenta, 'actividades': acts_con_entrega}

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
            if prof and check_password_hash(prof["password"], password):
                session.permanent = True
                session["profesor"] = usuario
                if prof.get('password_temporal'):
                    return redirect(url_for('profesor_cambiar_contrasena'))
                return redirect(url_for("profesor_dashboard"))
            else:
                error = "Usuario o contraseña incorrectos."
    return render_template("profesor_login.html", error=error)

@app.route("/profesor/logout")
def profesor_logout():
    session.pop("profesor", None)
    return redirect(url_for("profesor_login"))

@app.route('/profesor/recuperar_contrasena', methods=['GET', 'POST'])
def profesor_recuperar_contrasena():
    mensaje = None
    error = None
    if request.method == 'POST':
        usuario = request.form.get('usuario', '').strip()
        profesor = get_profesor(usuario)
        if profesor:
            nueva_temporal = _generar_password_temporal()
            con = get_db()
            con.execute("UPDATE profesores SET password=?, password_temporal=1 WHERE usuario=?",
                        (generate_password_hash(nueva_temporal), usuario))
            con.commit()
            con.close()
            mensaje = f"Tu nueva contraseña temporal es: {nueva_temporal}. Al iniciar sesión con ella te pediremos que la cambies por una de tu elección."
        else:
            error = "No se encontró ningún profesor con ese usuario."
    return render_template('recuperar_contrasena_prof.html', mensaje=mensaje, error=error)

@app.route('/profesor/cambiar_contrasena', methods=['GET', 'POST'])
def profesor_cambiar_contrasena():
    if 'profesor' not in session: return redirect(url_for('profesor_login'))
    usuario_actual = session['profesor']
    profesor = get_profesor(usuario_actual)
    error = None
    if request.method == 'POST':
        password_actual = request.form.get('password_actual', '')
        password_nueva = request.form.get('password_nueva', '')
        password_confirmar = request.form.get('password_confirmar', '')
        if not check_password_hash(profesor['password'], password_actual):
            error = "Tu contraseña actual no es correcta."
        elif len(password_nueva) < 6:
            error = "La nueva contraseña debe tener al menos 6 caracteres."
        elif password_nueva != password_confirmar:
            error = "La confirmación no coincide con la nueva contraseña."
        else:
            con = get_db()
            con.execute("UPDATE profesores SET password=?, password_temporal=0 WHERE usuario=?",
                        (generate_password_hash(password_nueva), usuario_actual))
            con.commit()
            con.close()
            return redirect(url_for('profesor_dashboard'))
    return render_template('cambiar_contrasena_prof.html', error=error,
                            era_temporal=bool(profesor.get('password_temporal')))

@app.route("/profesor/dashboard")
def profesor_dashboard():
    if "profesor" not in session:
        return redirect(url_for("profesor_login"))
    nombre_profesor = get_profesor(session["profesor"])["nombre"]

    conexion = sqlite3.connect("base_dts.db")
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

    conexion = sqlite3.connect("base_dts.db")
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
        if adm and check_password_hash(adm["password"], password):
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

    conexion = sqlite3.connect("base_dts.db")
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
        carrera = alumno_row.get("carrera") if alumno_row else None
        if cuenta not in alumnos:
            alumnos[cuenta] = {"nombre": nombre_alumno, "cuenta": cuenta,
                               "carrera": CARRERAS.get(carrera, carrera or "—"), "evaluaciones": []}
        alumnos[cuenta]["evaluaciones"].append({
            "materia": materia,
            "estilo": estilo,
            "recomendacion_ia": rec_ia,
            "recomendacion_corregida": rec_corregida,
            "profesor_corrector": prof_corrector,
            "fecha_correccion": fecha
        })

    total_alumnos = len(get_todos_alumnos())
    total_profesores = len(get_todos_profesores())
    return render_template("admin_dashboard.html",
                           admin=nombre_admin,
                           admin_activo=session["admin"],
                           alumnos=alumnos.values(),
                           total_alumnos=total_alumnos,
                           total_profesores=total_profesores,
                           total_alumnos_evaluados=total_alumnos_evaluados,
                           total_evaluaciones=total_evaluaciones,
                           total_correcciones=total_correcciones,
                           estilos_stats=estilos_stats)

@app.route("/admin/alumnos")
def admin_alumnos():
    if "admin" not in session:
        return redirect(url_for("admin_login"))
    nombre_admin = get_admin(session["admin"])["nombre"]
    return render_template("admin_alumnos.html",
                           admin=nombre_admin,
                           admin_activo=session["admin"],
                           base_alumnos=get_todos_alumnos(),
                           carreras=CARRERAS)

@app.route("/admin/profesores")
def admin_profesores():
    if "admin" not in session:
        return redirect(url_for("admin_login"))
    nombre_admin = get_admin(session["admin"])["nombre"]
    todos_profesores = get_todos_profesores()
    carreras_por_profesor = {usuario: obtener_carreras_profesor(usuario) for usuario in todos_profesores}
    nombres_carreras_por_profesor = {
        usuario: ", ".join(CARRERAS[c] for c in lista)
        for usuario, lista in carreras_por_profesor.items()
    }
    return render_template("admin_profesores.html",
                           admin=nombre_admin,
                           admin_activo=session["admin"],
                           profesores=todos_profesores,
                           carreras=CARRERAS,
                           carreras_por_profesor=carreras_por_profesor,
                           nombres_carreras_por_profesor=nombres_carreras_por_profesor)

@app.route("/admin/administradores")
def admin_administradores():
    if "admin" not in session:
        return redirect(url_for("admin_login"))
    nombre_admin = get_admin(session["admin"])["nombre"]
    return render_template("admin_administradores.html",
                           admin=nombre_admin,
                           admin_activo=session["admin"],
                           admins=get_todos_admins())

@app.route("/admin/agregar_alumno", methods=["POST"])
def admin_agregar_alumno():
    if "admin" not in session:
        return redirect(url_for("admin_login"))
    cuenta = request.form["cuenta"].strip()
    nombre = request.form["nombre"].strip()
    password = request.form["password"].strip()
    carrera = request.form["carrera"].strip()
    fecha_nacimiento = request.form.get("fecha_nacimiento", "").strip()
    if cuenta and nombre and password and carrera in CARRERAS and fecha_nacimiento:
        con = get_db()
        con.execute("INSERT OR REPLACE INTO alumnos (cuenta, password, nombre, carrera, fecha_nacimiento) VALUES (?,?,?,?,?)",
                     (cuenta, generate_password_hash(password), nombre, carrera, fecha_nacimiento))
        con.commit()
        con.close()
    return redirect(url_for("admin_alumnos"))

@app.route("/admin/agregar_profesor", methods=["POST"])
def admin_agregar_profesor():
    if "admin" not in session:
        return redirect(url_for("admin_login"))
    usuario = request.form["usuario"].strip()
    nombre = request.form["nombre"].strip()
    password = request.form["password"].strip()
    fecha_nacimiento = request.form.get("fecha_nacimiento", "").strip()
    carreras_validas = [c for c in request.form.getlist("carreras") if c in CARRERAS]
    if usuario and nombre and password and fecha_nacimiento and carreras_validas:
        con = get_db()
        con.execute("INSERT OR REPLACE INTO profesores (usuario, password, nombre, fecha_nacimiento) VALUES (?,?,?,?)",
                     (usuario, generate_password_hash(password), nombre, fecha_nacimiento))
        con.execute("DELETE FROM profesor_carreras WHERE usuario=?", (usuario,))
        for carrera in carreras_validas:
            con.execute("INSERT INTO profesor_carreras (usuario, carrera) VALUES (?,?)", (usuario, carrera))
        con.commit()
        con.close()
    return redirect(url_for("admin_profesores"))


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
        con.execute("DELETE FROM entregas_actividad_ia WHERE cuenta=?", (cuenta,))
        con.execute("DELETE FROM actividades_ia WHERE cuenta=?", (cuenta,))
        con.execute("DELETE FROM tareas_profesor WHERE cuenta=?", (cuenta,))
        con.commit()
        con.close()
    return redirect(url_for("admin_alumnos"))

@app.route("/admin/eliminar_profesor", methods=["POST"])
def admin_eliminar_profesor():
    if "admin" not in session:
        return redirect(url_for("admin_login"))
    usuario = request.form["usuario"].strip()
    if usuario:
        con = get_db()
        con.execute("DELETE FROM profesores WHERE usuario=?", (usuario,))
        con.execute("DELETE FROM profesor_carreras WHERE usuario=?", (usuario,))
        con.commit()
        con.close()
    return redirect(url_for("admin_profesores"))

@app.route("/admin/agregar_admin", methods=["POST"])
def admin_agregar_admin():
    if "admin" not in session:
        return redirect(url_for("admin_login"))
    usuario = request.form["usuario"].strip()
    nombre  = request.form["nombre"].strip()
    password = request.form["password"].strip()
    if usuario and nombre and password:
        con = get_db()
        con.execute("INSERT OR REPLACE INTO administradores VALUES (?,?,?)", (usuario, generate_password_hash(password), nombre))
        con.commit()
        con.close()
    return redirect(url_for("admin_administradores"))

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
    return redirect(url_for("admin_administradores"))


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

@app.route('/entregar_actividad_ia/<int:actividad_id>', methods=['POST'])
def entregar_actividad_ia(actividad_id):
    if 'usuario' not in session:
        return redirect(url_for('login'))
    from datetime import datetime
    cuenta = session['usuario']

    con = get_db()
    actividad = con.execute(
        "SELECT * FROM actividades_ia WHERE id=? AND cuenta=?", (actividad_id, cuenta)).fetchone()
    if not actividad:
        con.close()
        return redirect(url_for('mis_actividades'))

    contenido_texto = request.form.get('contenido_texto', '').strip()
    archivo_nombre, archivo_ext = None, None
    if 'archivo_entrega' in request.files:
        archivo = request.files['archivo_entrega']
        if archivo and archivo.filename and allowed_file(archivo.filename):
            archivo_ext = archivo.filename.rsplit('.', 1)[1].lower()
            archivo_nombre = secure_filename(f"entrega_act_{cuenta}_{actividad_id}_{archivo.filename}")
            archivo.save(os.path.join(app.config['UPLOAD_FOLDER'], archivo_nombre))

    if not contenido_texto and not archivo_nombre:
        con.close()
        return redirect(url_for('mis_actividades'))

    fecha = datetime.now().strftime('%d/%m/%Y %H:%M')
    con.execute("DELETE FROM entregas_actividad_ia WHERE actividad_id=? AND cuenta=?", (actividad_id, cuenta))
    con.execute("""INSERT INTO entregas_actividad_ia (actividad_id, cuenta, contenido_texto, archivo, fecha_entrega, estado)
                   VALUES (?,?,?,?,?,'pendiente')""", (actividad_id, cuenta, contenido_texto, archivo_nombre, fecha))
    con.commit()

    archivo_path = os.path.join(app.config['UPLOAD_FOLDER'], archivo_nombre) if archivo_nombre else None
    descripcion_actividad = actividad['actividad_corregida'] or actividad['actividad']
    resultado = _calificar_actividad_con_ia(
        actividad['materia'], actividad['estilo'], actividad['titulo'], descripcion_actividad,
        contenido_texto, archivo_path, archivo_ext)

    if resultado:
        con.execute("""UPDATE entregas_actividad_ia
                       SET calificacion=?, criterios=?, explicacion=?, estado='calificada', fecha_calificacion=?
                       WHERE actividad_id=? AND cuenta=?""",
                    (resultado['calificacion_total'], json.dumps(resultado['criterios']), resultado['explicacion'],
                     fecha, actividad_id, cuenta))
    else:
        con.execute("UPDATE entregas_actividad_ia SET estado='error' WHERE actividad_id=? AND cuenta=?",
                    (actividad_id, cuenta))
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

    # Generar todas las gráficas
    img_pastel   = g_pastel()
    img_estilos  = g_barras_estilos()
    img_materias = g_materias()
    img_dona     = g_dona()

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

    # Fila: materias | dona — juntas
    fila_g2 = []
    if img_materias: fila_g2.append(img_materias)
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

    story.append(PageBreak())

    # ══ PÁGINA 3: Padrón de alumnos ══════════════════════════════════════
    story.append(Paragraph("3. Padron de Alumnos", s_sec))
    al_data = [["#","Nombre","No. Cuenta","Carrera","Materias eval."]]
    for i, al in enumerate(alumnos_db, 1):
        mats = eval_por_cuenta.get(al["cuenta"], [])
        al_data.append([str(i), al["nombre"], al["cuenta"],
                        CARRERAS.get(al["carrera"], al["carrera"] or "—"),
                        str(len(mats))])
    story.append(mk_tabla(al_data, [0.3*inch, 2.6*inch, 1.2*inch, 1.7*inch, 1.1*inch]))
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
            Paragraph(f"{al['nombre']}  ·  {al['cuenta']}  ·  {CARRERAS.get(al['carrera'], al['carrera'] or '—')}", s_b),
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
            f"Documento generado automaticamente — Sistema de Estilos de Aprendizaje — Facultad de Estudios Superiores Campo 4 — {fecha_reporte}",
            s_pie),
    ]

    doc.build(story)
    buffer.seek(0)
    from flask import send_file as sf
    nombre = f"Reporte_Administrativo_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
    return sf(buffer, as_attachment=True, download_name=nombre, mimetype='application/pdf')


if __name__ == "__main__":
    app.run(debug=True, threaded=True)