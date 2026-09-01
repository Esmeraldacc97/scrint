from django.contrib import admin
from .models import PlanningSession, Participant, Estimation

@admin.register(PlanningSession)
class PlanningSessionAdmin(admin.ModelAdmin):
    list_display = ('id', 'project', 'created_at')  # Eliminar 'updated_at' si no está en models.py

@admin.register(Participant)
class ParticipantAdmin(admin.ModelAdmin):
    list_display = ('id', 'session', 'user')  # Eliminar 'role' si no está en models.py

@admin.register(Estimation)
class EstimationAdmin(admin.ModelAdmin):
    list_display = ('id', 'user_story', 'user', 'estimation_value')  # Cambiar 'participant' por 'user', 'points' por 'estimation_value'

