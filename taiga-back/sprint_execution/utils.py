# sprint_execution/utils.py

from django.db.models import Avg, Count, Q, Sum
from django.core.cache import cache
from datetime import datetime, timedelta
from taiga.projects.models import Membership
from taiga.users.models import User


class SprintMetricsCalculator:
    """Clase para calcular métricas del sprint"""
    
    def __init__(self, sprint):
        self.sprint = sprint
    
    def calculate_velocity(self):
        """Calcula la velocidad del sprint (puntos completados)"""
        return self.sprint.user_stories.filter(
            is_closed=True
        ).aggregate(total=Sum('points'))['total'] or 0
    
    def calculate_commitment_accuracy(self):
        """Calcula qué tan precisa fue la estimación inicial"""
        planned = self.sprint.user_stories.aggregate(
            total=Sum('points')
        )['total'] or 0
        
        completed = self.calculate_velocity()
        
        if planned > 0:
            return (completed / planned) * 100
        return 0
    
    def calculate_burndown_data(self):
        """Calcula los datos para el burndown chart"""
        start_date = self.sprint.estimated_start
        end_date = self.sprint.estimated_finish
        total_days = (end_date - start_date).days + 1
        
        total_points = self.sprint.user_stories.aggregate(
            total=Sum('points')
        )['total'] or 0
        
        ideal_line = []
        real_line = []
        
        for day in range(total_days):
            current_date = start_date + timedelta(days=day)
            
            # Línea ideal
            remaining_ideal = total_points - (total_points / total_days * day)
            ideal_line.append({
                'date': current_date,
                'points': remaining_ideal
            })
            
            # Línea real - puntos que quedan por completar
            completed_points = self.sprint.user_stories.filter(
                is_closed=True,
                modified_date__date__lte=current_date
            ).aggregate(total=Sum('points'))['total'] or 0
            
            remaining_real = total_points - completed_points
            real_line.append({
                'date': current_date,
                'points': remaining_real
            })
        
        return {
            'ideal': ideal_line,
            'real': real_line,
            'total_points': total_points
        }
    
    def get_team_performance_metrics(self):
        """Obtiene métricas de rendimiento del equipo"""
        # Tareas por miembro del equipo
        from taiga.projects.tasks.models import Task
        
        team_metrics = []
        members = Membership.objects.filter(
            project=self.sprint.project
        ).exclude(
            role__slug='stakeholder'
        )
        
        for member in members:
            tasks_assigned = Task.objects.filter(
                milestone=self.sprint,
                assigned_to=member.user
            ).count()
            
            tasks_completed = Task.objects.filter(
                milestone=self.sprint,
                assigned_to=member.user,
                status__is_closed=True
            ).count()
            
            team_metrics.append({
                'user': member.user,
                'user_name': member.user.get_full_name() or member.user.username,
                'role': member.role.name,
                'tasks_assigned': tasks_assigned,
                'tasks_completed': tasks_completed,
                'completion_rate': (tasks_completed / tasks_assigned * 100) if tasks_assigned > 0 else 0
            })
        
        return team_metrics


class ReviewAggregator:
    """Clase para agregar datos de reviews"""
    
    def __init__(self, sprint):
        self.sprint = sprint
        self.reviews = SprintReviewEntry.objects.filter(sprint=sprint)
    
    def get_summary(self):
        """Obtiene un resumen de todos los reviews"""
        if not self.reviews.exists():
            return {
                'total_reviews': 0,
                'average_satisfaction': 0,
                'average_code_quality': 0,
                'average_functionality': 0,
                'approval_rate': 0,
                'requires_changes': []
            }
        
        avg_satisfaction = self.reviews.aggregate(
            avg=Avg('satisfaction_level')
        )['avg'] or 0
        
        avg_code_quality = self.reviews.exclude(
            code_quality_rating__isnull=True
        ).aggregate(avg=Avg('code_quality_rating'))['avg'] or 0
        
        avg_functionality = self.reviews.exclude(
            functionality_rating__isnull=True
        ).aggregate(avg=Avg('functionality_rating'))['avg'] or 0
        
        total_reviews = self.reviews.count()
        approved_reviews = self.reviews.filter(sprint_approved=True).count()
        approval_rate = (approved_reviews / total_reviews * 100) if total_reviews > 0 else 0
        
        # Recopilar todos los cambios requeridos
        requires_changes = list(self.reviews.exclude(
            requires_changes__isnull=True
        ).exclude(
            requires_changes=''
        ).values_list('requires_changes', flat=True))
        
        return {
            'total_reviews': total_reviews,
            'average_satisfaction': round(avg_satisfaction, 2),
            'average_code_quality': round(avg_code_quality, 2),
            'average_functionality': round(avg_functionality, 2),
            'approval_rate': round(approval_rate, 2),
            'requires_changes': requires_changes
        }
    
    def get_story_feedback_summary(self):
        """Obtiene resumen de feedback por historia"""
        story_feedback = {}
        
        for review in self.reviews:
            for story_id, feedback in review.completed_stories_feedback.items():
                if story_id not in story_feedback:
                    story_feedback[story_id] = {
                        'ratings': [],
                        'approvals': 0,
                        'comments': []
                    }
                
                if feedback.get('rating'):
                    story_feedback[story_id]['ratings'].append(feedback['rating'])
                
                if feedback.get('approved'):
                    story_feedback[story_id]['approvals'] += 1
                
                if feedback.get('comments'):
                    story_feedback[story_id]['comments'].append({
                        'user': review.user.get_full_name() or review.user.username,
                        'comment': feedback['comments']
                    })
        
        # Calcular promedios
        for story_id, data in story_feedback.items():
            if data['ratings']:
                data['average_rating'] = sum(data['ratings']) / len(data['ratings'])
            else:
                data['average_rating'] = 0
            
            data['approval_rate'] = (data['approvals'] / self.reviews.count() * 100) if self.reviews.count() > 0 else 0
        
        return story_feedback


class RetrospectiveVotingManager:
    """Gestiona el sistema de votación de retrospectivas"""
    
    def __init__(self, sprint_id):
        self.sprint_id = sprint_id
        self.cache_timeout = 86400  # 24 horas
    
    def vote(self, user_id, item_type, item_index):
        """Registra un voto"""
        vote_key = f"retro_vote_{self.sprint_id}_{item_type}_{item_index}"
        user_vote_key = f"user_voted_{self.sprint_id}_{user_id}_{item_type}_{item_index}"
        
        # Verificar si ya votó
        if cache.get(user_vote_key):
            return None, "Ya has votado por este item"
        
        # Incrementar contador
        current_votes = cache.get(vote_key, 0)
        new_votes = current_votes + 1
        cache.set(vote_key, new_votes, timeout=self.cache_timeout)
        cache.set(user_vote_key, True, timeout=self.cache_timeout)
        
        return new_votes, "Voto registrado exitosamente"
    
    def get_votes(self, item_type, item_index):
        """Obtiene el número de votos para un item"""
        vote_key = f"retro_vote_{self.sprint_id}_{item_type}_{item_index}"
        return cache.get(vote_key, 0)
    
    def has_user_voted(self, user_id, item_type, item_index):
        """Verifica si un usuario ya votó"""
        user_vote_key = f"user_voted_{self.sprint_id}_{user_id}_{item_type}_{item_index}"
        return bool(cache.get(user_vote_key))
    
    def get_all_votes(self, retrospective):
        """Obtiene todos los votos para una retrospectiva"""
        votes = {
            'went_well': [],
            'to_improve': []
        }
        
        for idx, item in enumerate(retrospective.went_well):
            votes['went_well'].append({
                'index': idx,
                'text': item.get('text', ''),
                'votes': self.get_votes('went_well', idx)
            })
        
        for idx, item in enumerate(retrospective.to_improve):
            votes['to_improve'].append({
                'index': idx,
                'text': item.get('text', ''),
                'votes': self.get_votes('to_improve', idx)
            })
        
        return votes
    
    def clear_all_votes(self):
        """Limpia todos los votos de un sprint (usar con cuidado)"""
        # En producción, usar Redis y pattern matching
        # Por ahora, no hay una forma directa con el cache de Django
        pass


class SprintNotificationService:
    """Servicio para enviar notificaciones relacionadas con el sprint"""
    
    @staticmethod
    def notify_review_update(sprint, user, action='updated'):
        """Notifica cuando se actualiza un review"""
        from .sse import send_sse_message
        
        send_sse_message(
            event='sprint_review_updated',
            data={
                'project_id': sprint.project.id,
                'sprint_id': sprint.id,
                'sprint_name': sprint.name,
                'user': user.username,
                'user_full_name': user.get_full_name(),
                'action': action,
                'timestamp': datetime.now().isoformat()
            }
        )
    
    @staticmethod
    def notify_retrospective_update(sprint, user, action='updated'):
        """Notifica cuando se actualiza una retrospectiva"""
        from .sse import send_sse_message
        
        send_sse_message(
            event='retrospective_updated',
            data={
                'project_id': sprint.project.id,
                'sprint_id': sprint.id,
                'sprint_name': sprint.name,
                'user': user.username,
                'action': action,
                'timestamp': datetime.now().isoformat()
            }
        )
    
    @staticmethod
    def notify_sprint_closure(sprint, user):
        """Notifica cuando se cierra un sprint"""
        from .sse import send_sse_message
        
        send_sse_message(
            event='sprint_closed',
            data={
                'project_id': sprint.project.id,
                'sprint_id': sprint.id,
                'sprint_name': sprint.name,
                'closed_by': user.username,
                'timestamp': datetime.now().isoformat()
            }
        )


def get_user_role_in_project(user, project):
    """Obtiene el rol de un usuario en un proyecto"""
    try:
        membership = Membership.objects.get(
            user=user,
            project=project
        )
        return membership.role
    except Membership.DoesNotExist:
        return None


def can_user_approve_sprint(user, sprint):
    """Verifica si un usuario puede aprobar un sprint"""
    role = get_user_role_in_project(user, sprint.project)
    return role and role.slug == 'product-owner'


def can_user_manage_retrospective(user, sprint):
    """Verifica si un usuario puede gestionar retrospectivas"""
    role = get_user_role_in_project(user, sprint.project)
    return role and role.slug == 'scrum-master'


def format_date_for_export(date_value):
    """Formatea una fecha para exportación"""
    if date_value:
        if hasattr(date_value, 'strftime'):
            return date_value.strftime('%d/%m/%Y')
        return str(date_value)
    return ''