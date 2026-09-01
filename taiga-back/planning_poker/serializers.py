from rest_framework import serializers
from .models import PlanningSession, Participant, Estimation
from django.contrib.auth import get_user_model
from taiga.projects.userstories.models import UserStory


User = get_user_model()


class PlanningSessionSerializer(serializers.ModelSerializer):
    name = serializers.CharField()
    user_stories = serializers.PrimaryKeyRelatedField(
        many=True, queryset=UserStory.objects.all()
    )

    class Meta:
        model = PlanningSession
        fields = '__all__'
        read_only_fields = ['created_by']  # ✅ Esto evita que lo exija en la petición

    def validate_project(self, value):
        """ Asegura que el proyecto es válido """
        if hasattr(value, 'is_active') and not value.is_active:
            raise serializers.ValidationError("El proyecto no está activo.")
        return value

    def validate_user_stories(self, value):
        project_id = self.initial_data.get('project')
        if project_id:
            for story in value:
                if story.project_id != int(project_id):
                    raise serializers.ValidationError("Una o más historias no pertenecen al proyecto.")
        return value

    def create(self, validated_data):
        validated_data["created_by"] = self.context["request"].user
        return super().create(validated_data)

class UserBasicSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "full_name"]

class ParticipantSerializer(serializers.ModelSerializer):
    """ Serializer para los participantes """
    user = UserBasicSerializer(read_only=True)  # anidar los datos del usuario
    role = serializers.CharField() 

    class Meta:
        model = Participant
        fields = ['id', 'session', 'user', 'joined_at', 'role']

    def validate(self, data):
        """ Verifica que un usuario no se registre dos veces en una misma sesión """
        session = data['session']
        user = data['user']

        if Participant.objects.filter(session=session, user=user).exists():
            raise serializers.ValidationError("Este usuario ya está registrado en la sesión.")
        return data


class EstimationSerializer(serializers.ModelSerializer):
    def validate_estimation_value(self, value):
        fibonacci_values = {0, 1, 2, 3, 5, 8, 13, 20, 40, 100}
        if value not in fibonacci_values:
            raise serializers.ValidationError(
                "La estimación debe ser un número de la secuencia de Fibonacci (0,1,2,3,5,8,13,20,40,100)."
            )
        return value
    
    class Meta:
        model = Estimation
        fields = '__all__'

    def create(self, validated_data):
        """
        Si ya existe una estimación para la misma sesión, user_story y usuario, se actualiza en lugar de crear una nueva.
        """
        estimation, created = Estimation.objects.update_or_create(
            session=validated_data["session"],
            user_story=validated_data["user_story"],
            user=validated_data["user"],
            defaults={"estimation_value": validated_data["estimation_value"]}
        )
        return estimation
    
class PlanningSessionStatusSerializer(serializers.ModelSerializer):
    total_participants = serializers.SerializerMethodField()
    total_estimations = serializers.SerializerMethodField()

    class Meta:
        model = PlanningSession
        fields = ["id", "is_active", "in_discussion", "total_participants", "total_estimations"]

    def get_total_participants(self, obj):
        return obj.participants.count()

    def get_total_estimations(self, obj):
        return obj.estimations.count()
