import os

class EvaluadorEstilosAprendizaje:
    def __init__(self):
        # Tus preguntas originales
        self.preguntas = [
            {"pregunta": "Prefiero aprender con diagramas, gráficos y mapas conceptuales", "estilo": "visual"},
            {"pregunta": "Recuerdo mejor la información cuando la veo escrita o en imágenes", "estilo": "visual"},
            {"pregunta": "Me gusta tomar apuntes y hacer esquemas visuales", "estilo": "visual"},
            {"pregunta": "Prefiero instrucciones escritas en lugar de orales", "estilo": "visual"},
            {"pregunta": "Disfruto viendo videos educativos y presentaciones", "estilo": "visual"},
            {"pregunta": "Aprendo mejor cuando escucho explicaciones o discusiones", "estilo": "auditivo"},
            {"pregunta": "Recuerdo información cuando la escucho en podcasts o audiolibros", "estilo": "auditivo"},
            {"pregunta": "Me gusta participar en debates y discusiones grupales", "estilo": "auditivo"},
            {"pregunta": "Prefiero que me den instrucciones verbalmente", "estilo": "auditivo"},
            {"pregunta": "Disfruto escuchar conferencias y charlas", "estilo": "auditivo"},
            {"pregunta": "Aprendo mejor haciendo las cosas y con experiencia práctica", "estilo": "kinestesico"},
            {"pregunta": "Prefiero actividades manuales y experimentos", "estilo": "kinestesico"},
            {"pregunta": "Me muevo mucho y uso gestos cuando explico algo", "estilo": "kinestesico"},
            {"pregunta": "Recuerdo mejor cuando practico físicamente", "estilo": "kinestesico"},
            {"pregunta": "Disfruto los juegos de rol y simulaciones prácticas", "estilo": "kinestesico"},
            {"pregunta": "Prefiero analizar problemas paso a paso de forma lógica", "estilo": "analitico"},
            {"pregunta": "Me gusta descomponer la información en partes más pequeñas", "estilo": "analitico"},
            {"pregunta": "Disfruto resolviendo problemas matemáticos y puzzles", "estilo": "analitico"},
            {"pregunta": "Prefiero seguir métodos estructurados y secuenciales", "estilo": "analitico"},
            {"pregunta": "Me gusta investigar y profundizar en los temas", "estilo": "analitico"}
        ]
        
        self.estilos = {
            "visual": {
                "nombre": "Visual",
                "descripcion": "Aprendes mejor a través de imágenes, diagramas, colores y representaciones visuales.",
                "tecnicas": ["Mapas mentales", "Diagramas de flujo", "Videos educativos", "Infografías", "Esquemas coloridos"]
            },
            "auditivo": {
                "nombre": "Auditivo", 
                "descripcion": "Aprendes mejor escuchando, discutiendo y a través de explicaciones orales.",
                "tecnicas": ["Grabar clases", "Participar en debates", "Escuchar podcasts", "Explicar a otros", "Usar rimas y canciones"]
            },
            "kinestesico": {
                "nombre": "Kinestésico",
                "descripcion": "Aprendes mejor mediante el movimiento, la práctica y la experiencia directa.",
                "tecnicas": ["Aprendizaje práctico", "Juegos de rol", "Experimentación", "Tomar descansos activos", "Usar objetos manipulativos"]
            },
            "analitico": {
                "nombre": "Analítico",
                "descripcion": "Aprendes mejor analizando, clasificando y siguiendo procesos lógicos paso a paso.",
                "tecnicas": ["Listas y categorías", "Resolver problemas", "Investigación detallada", "Diagramas lógicos", "Métodos sistemáticos"]
            }
        }

    def calcular_resultados(self, respuestas):
        """Calcula los resultados basados en las respuestas"""
        puntuaciones = {estilo: 0 for estilo in self.estilos.keys()}
        
        for respuesta in respuestas:
            estilo = respuesta["estilo"]
            puntuaciones[estilo] += respuesta["puntuacion"]
        
        # Calcular porcentajes
        total_puntos = sum(puntuaciones.values())
        porcentajes = {}
        for estilo, puntos in puntuaciones.items():
            porcentajes[estilo] = (puntos / total_puntos) * 100 if total_puntos > 0 else 0
        
        # Encontrar estilo predominante
        estilo_predominante = max(puntuaciones, key=puntuaciones.get)
        
        # Devolvemos todo empaquetado para la web
        return {
            "estilo_ganador": self.estilos[estilo_predominante],
            "todas_puntuaciones": puntuaciones,
            "porcentajes": porcentajes
        }

    # --- NUEVA FUNCIÓN PARA FLASK ---
    def evaluar_desde_web(self, lista_respuestas_usuario):
        """
        Recibe una lista simple de números [5, 4, 1, 2...] que vienen de la web
        y los une con las preguntas para poder calcular.
        """
        respuestas_estructuradas = []
        
        # Unimos cada número con su pregunta correspondiente
        for i, puntaje in enumerate(lista_respuestas_usuario):
            if i < len(self.preguntas): # Seguridad para no pasarnos
                pregunta_actual = self.preguntas[i]
                respuestas_estructuradas.append({
                    "estilo": pregunta_actual["estilo"],
                    "puntuacion": int(puntaje)
                })
        
        return self.calcular_resultados(respuestas_estructuradas)