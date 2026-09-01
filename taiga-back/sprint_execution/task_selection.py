from taiga.projects.userstories.models import UserStory
from taiga.projects.tasks.models import Task
from .models import SelectedTask


def obtener_tareas_por_historia(sprint_id):
    historias = UserStory.objects.filter(
        milestone_id=sprint_id,
        in_sprint_backlog=True
    )

    tareas_por_historia = []

    for historia in historias:
        tareas = Task.objects.filter(user_story=historia)
        tareas_info = []
        for t in tareas:
            fue_seleccionada = SelectedTask.objects.filter(task=t).exists()
            tareas_info.append({
                "id": t.id,
                "titulo": t.subject,
                "seleccionada": fue_seleccionada
            })

        tareas_por_historia.append({
            "historia_id": historia.id,
            "historia_titulo": historia.subject,
            "tareas": tareas_info
        })

    return tareas_por_historia
