# sprint_execution/serializers.py - VERSIÓN LIMPIA

from rest_framework import serializers
from django.db.models import Count
from .models import (
    DailyMeeting, DailyResponse, SprintReviewEntry, 
    SprintClosure, SprintRetrospective
)
from taiga.users.serializers import UserBasicInfoSerializer
from taiga.projects.models import Membership


class DailyResponseSerializer(serializers.ModelSerializer):
    """Serializador para las respuestas del Daily Meeting"""
    
    user = UserBasicInfoSerializer(read_only=True)
    has_blockers = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = DailyResponse
        fields = [
            'id', 'meeting', 'user',
            'yesterday_work', 'today_plan', 'blockers', 'mood',
            'created_at', 'updated_at', 'has_blockers'
        ]
        read_only_fields = ['id', 'user', 'created_at', 'updated_at', 'has_blockers']
    
    def validate(self, data):
        """Validación personalizada"""
        request = self.context.get('request')
        
        # Si no se proporciona user_id, usar el usuario actual
        if 'user_id' not in data and request:
            data['user_id'] = request.user.id
        
        # Validar que el usuario pertenezca al proyecto
        if 'meeting' in data and 'user_id' in data:
            meeting = data['meeting']
            user_id = data['user_id']
            
            try:
                membership = Membership.objects.get(
                    project=meeting.project,
                    user_id=user_id
                )
                
                # Validar que solo Development Team pueda responder
                if membership.role.slug in ['product-owner', 'scrum-master', 'stakeholder']:
                    raise serializers.ValidationError(
                        f"Los usuarios con rol {membership.role.name} no pueden participar en el Daily Meeting"
                    )
            except Membership.DoesNotExist:
                raise serializers.ValidationError(
                    "El usuario no es miembro del proyecto"
                )
        
        return data
    
    def create(self, validated_data):
        """Crear respuesta del daily"""
        # El usuario viene del contexto
        user = self.context['request'].user
        validated_data['user'] = user
        return super().create(validated_data)


class DailyMeetingListSerializer(serializers.ModelSerializer):
    """Serializador para listar Daily Meetings"""
    
    participants_count = serializers.SerializerMethodField()
    pending_count = serializers.SerializerMethodField()
    has_blockers = serializers.SerializerMethodField()
    sprint_name = serializers.CharField(source='sprint.name', read_only=True)
    
    class Meta:
        model = DailyMeeting
        fields = [
            'id', 'project', 'date', 'sprint', 'sprint_name',
            'created_at', 'is_active', 'participants_count',
            'pending_count', 'has_blockers'
        ]
        read_only_fields = ['id', 'created_at']
    
    def get_participants_count(self, obj):
        return obj.get_participants_count()
    
    def get_pending_count(self, obj):
        return len(obj.get_pending_members())
    
    def get_has_blockers(self, obj):
        return obj.responses.filter(blockers__isnull=False).exclude(blockers='').exists()


class DailyMeetingDetailSerializer(serializers.ModelSerializer):
    """Serializador detallado para Daily Meeting"""
    
    responses = DailyResponseSerializer(many=True, read_only=True)
    participants_count = serializers.SerializerMethodField()
    pending_members = serializers.SerializerMethodField()
    sprint_name = serializers.CharField(source='sprint.name', read_only=True)
    team_mood_summary = serializers.SerializerMethodField()
    
    class Meta:
        model = DailyMeeting
        fields = [
            'id', 'project', 'date', 'sprint', 'sprint_name',
            'created_at', 'is_active', 'responses',
            'participants_count', 'pending_members', 'team_mood_summary'
        ]
        read_only_fields = ['id', 'created_at']
    
    def get_participants_count(self, obj):
        return obj.get_participants_count()
    
    def get_pending_members(self, obj):
        pending = obj.get_pending_members()
        return UserBasicInfoSerializer(pending, many=True).data
    
    def get_team_mood_summary(self, obj):
        """Resumen del estado de ánimo del equipo"""
        mood_counts = obj.responses.values('mood').annotate(
            count=Count('mood')
        )
        return {item['mood']: item['count'] for item in mood_counts}


class DailyMeetingCreateSerializer(serializers.ModelSerializer):
    """Serializador para crear Daily Meeting"""
    
    class Meta:
        model = DailyMeeting
        fields = ['id', 'project', 'date', 'sprint', 'is_active']
        read_only_fields = ['id']
    
    def validate_date(self, value):
        """Validar que no exista un daily para esa fecha"""
        project = self.initial_data.get('project')
        if project and DailyMeeting.objects.filter(
            project_id=project,
            date=value
        ).exists():
            raise serializers.ValidationError(
                "Ya existe un Daily Meeting para esta fecha"
            )
        return value
    
    def validate(self, data):
        """Validaciones adicionales"""
        # Validar que el sprint pertenezca al proyecto
        if 'sprint' in data and data['sprint']:
            if data['sprint'].project != data['project']:
                raise serializers.ValidationError(
                    "El sprint no pertenece al proyecto seleccionado"
                )
        
        return data


class SprintReviewEntrySerializer(serializers.ModelSerializer):
    """Serializador mejorado para Sprint Review"""
    user_name = serializers.SerializerMethodField()
    user_role = serializers.SerializerMethodField()
    average_story_rating = serializers.SerializerMethodField()
    satisfaction_display = serializers.CharField(source='get_satisfaction_level_display', read_only=True)
    
    class Meta:
        model = SprintReviewEntry
        fields = [
            'id', 'sprint', 'user', 'user_name', 'user_role',
            'general_feedback', 'satisfaction_level', 'satisfaction_display',
            'completed_stories_feedback', 'sprint_approved', 'requires_changes',
            'code_quality_rating', 'functionality_rating',
            'average_story_rating', 'created_at', 'updated_at'
        ]
        read_only_fields = ['user', 'created_at', 'updated_at']
    
    def get_user_name(self, obj):
        return obj.user.get_full_name() or obj.user.username
    
    def get_user_role(self, obj):
        try:
            membership = Membership.objects.get(
                project=obj.sprint.project,
                user=obj.user
            )
            return membership.role.name
        except Membership.DoesNotExist:
            return "Unknown"
    
    def get_average_story_rating(self, obj):
        return round(obj.get_average_story_rating(), 2)
    
    def validate_satisfaction_level(self, value):
        if value not in range(1, 6):
            raise serializers.ValidationError("El nivel de satisfacción debe estar entre 1 y 5")
        return value
    
    def validate_completed_stories_feedback(self, value):
        """Validar estructura del feedback por historia"""
        if not isinstance(value, dict):
            raise serializers.ValidationError("El feedback de historias debe ser un diccionario")
        
        for story_id, feedback in value.items():
            if not isinstance(feedback, dict):
                raise serializers.ValidationError(f"El feedback para la historia {story_id} debe ser un diccionario")
            
            # Validar campos esperados
            if 'rating' in feedback and feedback['rating'] not in range(1, 6):
                raise serializers.ValidationError(f"El rating para la historia {story_id} debe estar entre 1 y 5")
        
        return value


class SprintClosureSerializer(serializers.ModelSerializer):
    """Serializador para Cierre de Sprint"""
    closed_by_name = serializers.SerializerMethodField()
    sprint_name = serializers.SerializerMethodField()
    project_name = serializers.SerializerMethodField()

    class Meta:
        model = SprintClosure
        fields = ["id", "sprint", "sprint_name",
            "project_name", "closed_at", "closed_by_name", "notes"]

    def create(self, validated_data):
        user = self.context["request"].user
        return SprintClosure.objects.create(closed_by=user, **validated_data)
    
    def get_closed_by_name(self, obj):
        if obj.closed_by:
            return obj.closed_by.get_full_name() or obj.closed_by.username
        return None
    
    def get_sprint_name(self, obj):
        return obj.sprint.name if obj.sprint else None

    def get_project_name(self, obj):
        return obj.sprint.project.name if obj.sprint and obj.sprint.project else None


class SprintRetrospectiveSerializer(serializers.ModelSerializer):
    """Serializador mejorado para Retrospectiva"""
    sprint_name = serializers.CharField(source="sprint.name", read_only=True)
    project_name = serializers.CharField(source="sprint.project.name", read_only=True)
    created_by_name = serializers.SerializerMethodField()
    team_mood_display = serializers.CharField(source='get_team_mood_display', read_only=True)
    completion_percentage = serializers.SerializerMethodField()
    
    class Meta:
        model = SprintRetrospective
        fields = [
            "id", "sprint", "sprint_name", "project_name",
            "created_by", "created_by_name", "created_at", "updated_at",
            "went_well", "to_improve", "action_items",
            "team_mood", "team_mood_display",
            "velocity_achieved", "commitment_accuracy", "completion_percentage",
            "previous_actions_completed"
        ]
        read_only_fields = ["created_by", "created_at", "updated_at", "velocity_achieved"]
    
    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name() or obj.created_by.username
        return "Unknown"
    
    def get_completion_percentage(self, obj):
        if obj.commitment_accuracy:
            return f"{float(obj.commitment_accuracy):.2f}%"
        return "0.00%"
    
    def validate_went_well(self, value):
        """Validar estructura de items que salieron bien"""
        if not isinstance(value, list):
            raise serializers.ValidationError("'went_well' debe ser una lista")
        
        for idx, item in enumerate(value):
            if not isinstance(item, dict):
                raise serializers.ValidationError(f"El item {idx} en 'went_well' debe ser un diccionario")
            if 'text' not in item or not item['text'].strip():
                raise serializers.ValidationError(f"El item {idx} en 'went_well' debe tener un texto no vacío")
        
        return value
    
    def validate_to_improve(self, value):
        """Validar estructura de items a mejorar"""
        if not isinstance(value, list):
            raise serializers.ValidationError("'to_improve' debe ser una lista")
        
        for idx, item in enumerate(value):
            if not isinstance(item, dict):
                raise serializers.ValidationError(f"El item {idx} en 'to_improve' debe ser un diccionario")
            if 'text' not in item or not item['text'].strip():
                raise serializers.ValidationError(f"El item {idx} en 'to_improve' debe tener un texto no vacío")
        
        return value
    
    def validate_action_items(self, value):
        """Validar estructura de acciones"""
        if not isinstance(value, list):
            raise serializers.ValidationError("'action_items' debe ser una lista")
        
        for idx, action in enumerate(value):
            if not isinstance(action, dict):
                raise serializers.ValidationError(f"La acción {idx} debe ser un diccionario")
            
            # Validar campos requeridos
            if 'action' not in action or not action['action'].strip():
                raise serializers.ValidationError(f"La acción {idx} debe tener una descripción")
            
            if 'responsible_id' in action and action['responsible_id']:
                # Validar que el usuario existe
                try:
                    User.objects.get(id=action['responsible_id'])
                except User.DoesNotExist:
                    raise serializers.ValidationError(
                        f"El responsable con ID {action['responsible_id']} no existe"
                    )
            
            # Validar formato de fecha si existe
            if 'due_date' in action and action['due_date']:
                try:
                    # Intentar parsear la fecha
                    from datetime import datetime
                    if isinstance(action['due_date'], str):
                        datetime.strptime(action['due_date'], '%Y-%m-%d')
                except ValueError:
                    raise serializers.ValidationError(
                        f"La fecha límite de la acción {idx} debe estar en formato YYYY-MM-DD"
                    )
        
        return value

class SprintReviewSummarySerializer(serializers.Serializer):
    """Serializador para resumen de Sprint Review"""
    sprint_id = serializers.IntegerField()
    sprint_name = serializers.CharField()
    total_reviews = serializers.IntegerField()
    average_satisfaction = serializers.FloatField()
    average_code_quality = serializers.FloatField()
    average_functionality = serializers.FloatField()
    approval_rate = serializers.FloatField()
    completed_stories_count = serializers.IntegerField()
    
    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Formatear porcentajes y promedios
        data['average_satisfaction'] = f"{data['average_satisfaction']:.2f}/5"
        data['average_code_quality'] = f"{data['average_code_quality']:.2f}/5"
        data['average_functionality'] = f"{data['average_functionality']:.2f}/5"
        data['approval_rate'] = f"{data['approval_rate']:.2f}%"
        return data


class RetrospectiveActionSerializer(serializers.Serializer):
    """Serializador para acciones de retrospectiva"""
    action = serializers.CharField(required=True)
    responsible_id = serializers.IntegerField(required=False, allow_null=True)
    responsible_name = serializers.SerializerMethodField()
    due_date = serializers.DateField(required=False, allow_null=True)
    completed = serializers.BooleanField(default=False)
    
    def get_responsible_name(self, obj):
        if obj.get('responsible_id'):
            try:
                user = User.objects.get(id=obj['responsible_id'])
                return user.get_full_name() or user.username
            except User.DoesNotExist:
                return "Usuario no encontrado"
        return "No asignado"