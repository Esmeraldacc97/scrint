from taiga.projects.userstories.models import UserStory
from taiga.projects.models import Project
from taiga.projects.tasks.models import Task
from django.contrib.auth import get_user_model

User = get_user_model()

# === CONFIGURA ESTOS VALORES ===
slug_proyecto = 'esmeraldacc-simulador-scrum'
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

# === TAREAS PARA HISTORIAS EXISTENTES ===
tareas_por_historia = {
    'Historia usuario 3': [
        'Permitir a los usuarios autenticarse.',
        'Bloquear después de 3 intentos fallidos'
    ],
    'Historia de usuario 4': [
        'Permitir a nuevos usuarios registrarse'
    ],
}

for subject_historia, lista_tareas in tareas_por_historia.items():
    try:
        historia = UserStory.objects.get(project=proyecto, subject=subject_historia)
        print(f"📌 Historia encontrada: {subject_historia}")
    except UserStory.DoesNotExist:
        print(f"❌ No se encontró la historia: {subject_historia}")
        continue

    for nombre_tarea in lista_tareas:
        tarea, creada = Task.objects.get_or_create(
            project=proyecto,
            user_story=historia,
            subject=nombre_tarea,
            defaults={'owner': usuario}
        )
        if creada:
            print(f"   ✅ Tarea creada: {nombre_tarea}")
        else:
            print(f"   ℹ️ Tarea ya existe: {nombre_tarea}")
