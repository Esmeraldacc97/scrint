from taiga.projects.userstories.models import UserStory
from taiga.projects.models import Project
from taiga.projects.tasks.models import Task
from django.contrib.auth import get_user_model

User = get_user_model()

# === CONFIGURA ESTOS VALORES ===
slug_proyecto = 'esmeraldacc-proyecto_hotel'
username_owner = 'esmeraldacc'

# === BUSCAR PROYECTO Y USUARIO ===
try:
    proyecto = Project.objects.get(slug=slug_proyecto)
    print(f"🔍 Proyecto encontrado: {proyecto.name}")
except Project.DoesNotExist:
    print(f"❌ No se encontró el proyecto con slug '{slug_proyecto}'")
    exit()

try:
    usuario = User.objects.get(username=username_owner)
    print(f"🔍 Usuario encontrado: {usuario.username}")
except User.DoesNotExist:
    print(f"❌ No se encontró el usuario '{username_owner}'")
    exit()

# === HISTORIAS Y TAREAS ===
historias = [
    # MÓDULO DE AUTENTICACIÓN Y USUARIOS
    {
        'subject': 'Crear Nuevo Usuario',
        'description': 'Como: Cliente del hotel\nQuiero: Crear una cuenta de usuario para el sitio web\nPara: Realizar mis reservas indicando mi Nombre, Correo electrónico y Contraseña',
        'tareas': [
            'Realizar la maquetación de la interfaz de registro nuevo usuario',
            'Crear validaciones para los campos necesarios',
            'Asegurar que el correo electrónico no esté registrado',
            'Validar la fortaleza de la contraseña',
            'Implementar confirmación de correo electrónico',
            'Desarrollar pruebas para verificar la creación de nuevo usuario'
        ]
    },
    {
        'subject': 'Iniciar Sesión de Usuario',
        'description': 'Como: Cliente registrado\nQuiero: Iniciar sesión en el sistema\nPara: Acceder a mis reservas y perfil personal',
        'tareas': [
            'Diseñar interfaz de login responsive',
            'Implementar autenticación con JWT',
            'Agregar opción de "Recordar contraseña"',
            'Implementar recuperación de contraseña por email',
            'Agregar captcha para prevenir ataques',
            'Crear tests de seguridad para el login'
        ]
    },
    
    # MÓDULO DE RESERVAS
    {
        'subject': 'Buscar Habitaciones Disponibles',
        'description': 'Como: Cliente\nQuiero: Buscar habitaciones disponibles por fechas\nPara: Encontrar opciones que se ajusten a mis necesidades de viaje',
        'tareas': [
            'Crear interfaz de búsqueda con calendario',
            'Implementar filtros por tipo de habitación',
            'Agregar filtro por rango de precios',
            'Mostrar disponibilidad en tiempo real',
            'Implementar vista de galería de habitaciones',
            'Optimizar consultas de búsqueda para rendimiento'
        ]
    },
    {
        'subject': 'Realizar Reserva de Habitación',
        'description': 'Como: Cliente autenticado\nQuiero: Reservar una habitación seleccionada\nPara: Asegurar mi hospedaje en las fechas deseadas',
        'tareas': [
            'Diseñar formulario de reserva paso a paso',
            'Validar disponibilidad antes de confirmar',
            'Implementar cálculo automático de precio total',
            'Agregar selección de servicios adicionales',
            'Integrar pasarela de pago',
            'Enviar confirmación por correo electrónico',
            'Generar código QR para check-in'
        ]
    },
    {
        'subject': 'Ver Historial de Reservas',
        'description': 'Como: Cliente registrado\nQuiero: Ver todas mis reservas pasadas y futuras\nPara: Gestionar mis viajes y tener acceso a la información',
        'tareas': [
            'Crear vista de listado de reservas',
            'Implementar filtros por estado (activa, pasada, cancelada)',
            'Agregar opción de descarga de comprobante PDF',
            'Mostrar detalles expandibles de cada reserva',
            'Implementar búsqueda por fecha o código'
        ]
    },
    
    # MÓDULO DE GESTIÓN DE HABITACIONES (ADMIN)
    {
        'subject': 'Administrar Catálogo de Habitaciones',
        'description': 'Como: Administrador del hotel\nQuiero: Gestionar el inventario de habitaciones\nPara: Mantener actualizada la información y disponibilidad',
        'tareas': [
            'Crear CRUD completo de habitaciones',
            'Implementar carga múltiple de imágenes',
            'Agregar editor de descripciones con formato',
            'Gestionar amenidades por habitación',
            'Configurar precios por temporada',
            'Implementar estado de mantenimiento'
        ]
    },
    {
        'subject': 'Gestionar Tarifas Dinámicas',
        'description': 'Como: Administrador\nQuiero: Configurar precios según temporada y ocupación\nPara: Optimizar los ingresos del hotel',
        'tareas': [
            'Crear calendario de temporadas',
            'Implementar reglas de precio por ocupación',
            'Configurar descuentos por estadía prolongada',
            'Agregar tarifas especiales para grupos',
            'Desarrollar simulador de precios'
        ]
    },
    
    # MÓDULO DE CHECK-IN/CHECK-OUT
    {
        'subject': 'Realizar Check-in Digital',
        'description': 'Como: Cliente con reserva\nQuiero: Hacer check-in desde mi móvil\nPara: Agilizar mi llegada al hotel',
        'tareas': [
            'Desarrollar interfaz móvil para check-in',
            'Implementar escaneo de código QR',
            'Validar documentos de identidad',
            'Asignar habitación automáticamente',
            'Generar llave digital',
            'Enviar notificación de habitación lista'
        ]
    },
    {
        'subject': 'Gestionar Check-out Express',
        'description': 'Como: Huésped\nQuiero: Realizar check-out rápido\nPara: Salir del hotel sin demoras',
        'tareas': [
            'Crear interfaz de check-out digital',
            'Mostrar resumen de consumos',
            'Procesar pagos pendientes',
            'Generar factura electrónica',
            'Solicitar evaluación del servicio',
            'Enviar recibo por email'
        ]
    },
    
    # MÓDULO DE SERVICIOS ADICIONALES
    {
        'subject': 'Solicitar Servicio a la Habitación',
        'description': 'Como: Huésped activo\nQuiero: Pedir servicios desde la app\nPara: Mejorar mi experiencia sin llamar a recepción',
        'tareas': [
            'Crear catálogo de servicios disponibles',
            'Implementar sistema de pedidos en tiempo real',
            'Agregar seguimiento de estado del pedido',
            'Integrar chat con servicio al cliente',
            'Notificar al personal correspondiente',
            'Registrar consumos en la cuenta'
        ]
    },
    {
        'subject': 'Reservar Amenidades del Hotel',
        'description': 'Como: Huésped\nQuiero: Reservar spa, restaurante, gimnasio\nPara: Planificar mis actividades en el hotel',
        'tareas': [
            'Mostrar calendario de disponibilidad',
            'Implementar reservas con horarios',
            'Enviar recordatorios automáticos',
            'Gestionar lista de espera',
            'Permitir cancelaciones con políticas'
        ]
    },
    
    # MÓDULO DE REPORTES Y ANALYTICS
    {
        'subject': 'Ver Dashboard de Ocupación',
        'description': 'Como: Gerente del hotel\nQuiero: Ver métricas de ocupación en tiempo real\nPara: Tomar decisiones informadas',
        'tareas': [
            'Crear dashboard con gráficos interactivos',
            'Mostrar ocupación actual y proyectada',
            'Implementar comparativas históricas',
            'Agregar alertas de baja ocupación',
            'Exportar reportes en Excel/PDF',
            'Crear vista móvil del dashboard'
        ]
    },
    {
        'subject': 'Generar Reportes Financieros',
        'description': 'Como: Administrador\nQuiero: Obtener reportes detallados de ingresos\nPara: Analizar el desempeño financiero del hotel',
        'tareas': [
            'Implementar reporte de ingresos por período',
            'Desglosar ingresos por tipo de habitación',
            'Mostrar ingresos por servicios adicionales',
            'Crear proyecciones basadas en reservas',
            'Comparar con períodos anteriores',
            'Integrar con sistema contable'
        ]
    },
    
    # MÓDULO DE COMUNICACIÓN
    {
        'subject': 'Enviar Notificaciones a Huéspedes',
        'description': 'Como: Personal del hotel\nQuiero: Comunicarme con los huéspedes\nPara: Informar sobre eventos o cambios importantes',
        'tareas': [
            'Implementar sistema de notificaciones push',
            'Crear plantillas de mensajes',
            'Segmentar huéspedes por criterios',
            'Programar envíos automáticos',
            'Rastrear lectura de notificaciones'
        ]
    },
    {
        'subject': 'Gestionar Reseñas y Calificaciones',
        'description': 'Como: Administrador\nQuiero: Gestionar las reseñas de los huéspedes\nPara: Mejorar la reputación online del hotel',
        'tareas': [
            'Solicitar reseñas post-estadía',
            'Moderar comentarios antes de publicar',
            'Responder a reseñas negativas',
            'Mostrar calificación promedio',
            'Integrar con TripAdvisor y Google',
            'Generar reportes de satisfacción'
        ]
    }
]

# === CREAR HISTORIAS Y TAREAS ===
print(f"\n📋 Creando {len(historias)} historias de usuario...\n")

contador_historias = 0
contador_tareas = 0

for h in historias:
    historia, creada = UserStory.objects.get_or_create(
        project=proyecto,
        subject=h['subject'],
        defaults={
            'description': h['description'],
            'owner': usuario
        }
    )
    if creada:
        print(f"✅ Historia creada: {h['subject']}")
        contador_historias += 1
    else:
        print(f"ℹ️  Historia existente: {h['subject']}")

    # Crear tareas para la historia
    for nombre_tarea in h['tareas']:
        tarea, creada_tarea = Task.objects.get_or_create(
            project=proyecto,
            user_story=historia,
            subject=nombre_tarea,
            defaults={'owner': usuario}
        )
        if creada_tarea:
            print(f"   🔧 Tarea creada: {nombre_tarea}")
            contador_tareas += 1
        else:
            print(f"   ℹ️  Tarea ya existe: {nombre_tarea}")

print(f"\n📊 Resumen:")
print(f"   - Historias creadas: {contador_historias}")
print(f"   - Tareas creadas: {contador_tareas}")
print(f"   - Total de historias en el proyecto: {UserStory.objects.filter(project=proyecto).count()}")
print(f"   - Total de tareas en el proyecto: {Task.objects.filter(project=proyecto).count()}")
print(f"\n✨ Proceso completado!")