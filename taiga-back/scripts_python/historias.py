from taiga.projects.userstories.models import UserStory
from taiga.projects.models import Project
from django.contrib.auth import get_user_model

User = get_user_model()

# === CONFIGURA ESTOS VALORES ===
slug_proyecto = 'esmeraldacc-m1101_cucharon'
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

# === HISTORIAS DE USUARIO DE PRUEBA ===
historias = [
    {'subject': '201 - Posteo de producto', 'description': 'Descripción de la historia'},
]

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
    else:
        print(f"ℹ️ La historia ya existía: {h['subject']}")
