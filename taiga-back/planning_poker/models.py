from django.db import models
from django.contrib.auth import get_user_model
from taiga.projects.models import Project
from taiga.projects.userstories.models import UserStory

User = get_user_model()

class PlanningSession(models.Model):
    """ Representa una sesión de Planning Poker en un proyecto """
    name = models.CharField(max_length=255, default="Sesión sin nombre")
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="planning_sessions")
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)
    in_discussion = models.BooleanField(default=True)  # Columna para manejar si la sesión sigue abierta
    in_discussion = models.BooleanField(default=True)  # Si sigue en discusión
    user_stories = models.ManyToManyField("userstories.UserStory", related_name="planning_sessions", blank=True)
    def __str__(self):
        
        return f"Planning Session for {self.project.name} - Active: {self.is_active}"

class Participant(models.Model):
    """ Representa un usuario que participa en una sesión de Planning Poker """
    session = models.ForeignKey(PlanningSession, on_delete=models.CASCADE, related_name="participants")
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    joined_at = models.DateTimeField(auto_now_add=True)
    role = models.CharField(
    max_length=50,
    choices=[
        ('DEV', 'Developer'),
        ('SM', 'Scrum Master'),
        ('PO', 'Product Owner')
    ],
    default='DEV'  # Agregar un valor por defecto
)

    def __str__(self):
        return f"{self.user.username} in {self.session}"

class Estimation(models.Model):
    """ Representa la estimación de un usuario en una historia de usuario """
    
    session = models.ForeignKey(PlanningSession, on_delete=models.CASCADE, related_name="estimations")
    user_story = models.ForeignKey(UserStory, on_delete=models.CASCADE, related_name="estimations")
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    estimation_value = models.IntegerField()  # Eliminamos choices para evitar validación interna de Django
    created_at = models.DateTimeField(auto_now_add=True)
    final = models.BooleanField(default=False)  # Nueva columna para identificar si la estimación es la final

    class Meta:
        unique_together = ("session", "user_story", "user")  # Evita múltiples estimaciones de un usuario en la misma historia
    
    def __str__(self):
        return f"Estimation by {self.user.username} - {self.estimation_value}"

