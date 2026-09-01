# sprint_execution/models.py - VERSIÓN LIMPIA

from django.db import models
from django.conf import settings
from django.utils.timezone import now
from taiga.projects.tasks.models import Task
from taiga.projects.userstories.models import UserStory
from taiga.projects.milestones.models import Milestone
from django.db.models import Sum


class SelectedTask(models.Model):
    """Tareas seleccionadas para el Sprint"""
    task = models.OneToOneField(Task, on_delete=models.CASCADE, related_name='selected_task')
    user_story = models.ForeignKey(UserStory, on_delete=models.CASCADE)
    selected_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Tarea seleccionada: {self.task.subject}"


class DailyMeeting(models.Model):
    """
    Representa una sesión de Daily Meeting para un proyecto en una fecha específica
    """
    project = models.ForeignKey(
        'projects.Project',
        null=False,
        blank=False,
        related_name="daily_meetings",
        verbose_name="project",
        on_delete=models.CASCADE
    )
    date = models.DateField(
        null=False,
        blank=False,
        default=now,
        verbose_name="meeting date"
    )
    sprint = models.ForeignKey(
        Milestone,
        null=True,
        blank=True,
        related_name="daily_meetings",
        verbose_name="sprint",
        on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="created at"
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="is active"
    )
    
    class Meta:
        verbose_name = "Daily Meeting"
        verbose_name_plural = "Daily Meetings"
        ordering = ['-date', '-created_at']
        unique_together = ['project', 'date']
    
    def __str__(self):
        return f"Daily Meeting - {self.project.name} - {self.date}"
    
    def get_participants_count(self):
        """Obtiene el número de participantes que han respondido"""
        return self.responses.count()
    
    def get_pending_members(self):
        """Obtiene los miembros que aún no han respondido"""
        from taiga.projects.models import Membership
        # Solo Development Team puede participar
        dev_team_memberships = Membership.objects.filter(
            project=self.project
        ).exclude(
            role__slug__in=['product-owner', 'scrum-master', 'stakeholder']
        )
        responded_users = self.responses.values_list('user_id', flat=True)
        pending_users = [m.user for m in dev_team_memberships if m.user.id not in responded_users]
        return pending_users


class DailyResponse(models.Model):
    """
    Respuesta individual de un miembro del equipo en el Daily Meeting
    """
    meeting = models.ForeignKey(
        DailyMeeting,
        null=False,
        blank=False,
        related_name="responses",
        verbose_name="daily meeting",
        on_delete=models.CASCADE
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=False,
        blank=False,
        related_name="daily_responses",
        verbose_name="user",
        on_delete=models.CASCADE
    )
    yesterday_work = models.TextField(
        null=False,
        blank=False,
        verbose_name="What did you do yesterday?",
        help_text="Describe what you accomplished yesterday"
    )
    today_plan = models.TextField(
        null=False,
        blank=False,
        verbose_name="What will you do today?",
        help_text="Describe what you plan to work on today"
    )
    blockers = models.TextField(
        null=True,
        blank=True,
        verbose_name="Any blockers?",
        help_text="Describe any impediments or blockers"
    )
    mood = models.CharField(
        max_length=20,
        choices=[
            ('great', 'Great 😊'),
            ('good', 'Good 🙂'),
            ('neutral', 'Neutral 😐'),
            ('bad', 'Bad 😕'),
            ('terrible', 'Terrible 😞')
        ],
        default='neutral',
        verbose_name="Team member mood"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="created at"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="updated at"
    )
    
    class Meta:
        verbose_name = "Daily Response"
        verbose_name_plural = "Daily Responses"
        ordering = ['-created_at']
        unique_together = ['meeting', 'user']
    
    def __str__(self):
        return f"{self.user.get_full_name()} - {self.meeting.date}"
    
    def has_blockers(self):
        """Verifica si el usuario reportó blockers"""
        return bool(self.blockers and self.blockers.strip())


class SprintReviewEntry(models.Model):
    """Feedback estructurado del Sprint Review"""
    
    SATISFACTION_CHOICES = [
        (1, 'Muy Insatisfecho'),
        (2, 'Insatisfecho'),
        (3, 'Neutral'),
        (4, 'Satisfecho'),
        (5, 'Muy Satisfecho')
    ]
    
    sprint = models.ForeignKey(Milestone, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    
    # Feedback general
    general_feedback = models.TextField()
    satisfaction_level = models.IntegerField(choices=SATISFACTION_CHOICES)
    
    # Feedback por historia
    completed_stories_feedback = models.JSONField(default=dict)
    # Formato: {"story_id": {"approved": bool, "comments": str, "rating": int}}
    
    # Aprobación formal
    sprint_approved = models.BooleanField(default=False)
    requires_changes = models.TextField(blank=True, null=True)
    
    # Métricas de calidad
    code_quality_rating = models.IntegerField(
        choices=[(i, i) for i in range(1, 6)],
        null=True, blank=True
    )
    functionality_rating = models.IntegerField(
        choices=[(i, i) for i in range(1, 6)],
        null=True, blank=True
    )
    
    # Metadatos
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['sprint', 'user']
        ordering = ['-created_at']
    
    def get_average_story_rating(self):
        """Calcula el rating promedio de las historias"""
        ratings = [
            feedback.get('rating', 0) 
            for feedback in self.completed_stories_feedback.values()
            if feedback.get('rating')
        ]
        return sum(ratings) / len(ratings) if ratings else 0


class SprintClosure(models.Model):
    """Cierre formal del Sprint"""
    sprint = models.OneToOneField(Milestone, on_delete=models.CASCADE, related_name="closure")
    closed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    closed_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Cierre de Sprint {self.sprint.name}"


class SprintRetrospective(models.Model):
    """Retrospectiva estructurada del Sprint"""
    
    MOOD_CHOICES = [
        ('terrible', 'Terrible 😞'),
        ('bad', 'Malo 😕'),
        ('neutral', 'Neutral 😐'),
        ('good', 'Bueno 🙂'),
        ('great', 'Excelente 😊')
    ]
    
    sprint = models.OneToOneField(
        Milestone, 
        on_delete=models.CASCADE, 
        related_name="retrospective"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True
    )
    
    # Reflexiones estructuradas
    went_well = models.JSONField(default=list)
    # Formato: [{"text": str, "votes": int, "author_id": int}]
    
    to_improve = models.JSONField(default=list)
    # Formato: [{"text": str, "votes": int, "author_id": int}]
    
    action_items = models.JSONField(default=list)
    # Formato: [{"action": str, "responsible_id": int, "due_date": date}]
    
    # Métricas del equipo
    team_mood = models.CharField(
        max_length=20, 
        choices=MOOD_CHOICES,
        default='neutral'
    )
    velocity_achieved = models.IntegerField(default=0)
    commitment_accuracy = models.DecimalField(
        max_digits=5, 
        decimal_places=2,
        null=True, 
        blank=True
    )
    
    # Seguimiento de acciones previas
    previous_actions_completed = models.JSONField(default=list)
    
    # Metadatos
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def calculate_commitment_accuracy(self):
        """Calcula qué tan precisa fue la estimación vs lo completado"""
        completed = self.sprint.user_stories.filter(is_closed=True).aggregate(
            total=Sum('points')
        )['total'] or 0
        
        planned = self.sprint.user_stories.aggregate(
            total=Sum('points')
        )['total'] or 0
        
        if planned > 0:
            self.commitment_accuracy = (completed / planned) * 100
            self.save()