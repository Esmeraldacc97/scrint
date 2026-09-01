from rest_framework.exceptions import ValidationError
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils.timezone import now 
import time
import traceback
from collections import deque
from django.db import models  # Para models.Avg
import pandas as pd
from io import BytesIO
from datetime import datetime
import xlsxwriter
from asgiref.sync import sync_to_async
from django.http import StreamingHttpResponse,HttpResponse
from django.db.models import Max
from taiga.projects.models import Project, Membership
from .models import PlanningSession, Participant, Estimation
from taiga.projects.userstories.models import UserStory
from taiga.projects.milestones.models import Milestone
from django.contrib.auth import get_user_model
from .serializers import PlanningSessionSerializer, ParticipantSerializer, EstimationSerializer, PlanningSessionStatusSerializer

User = get_user_model()

# Cola de mensajes para SSE (máximo 100 mensajes)
sse_message_queue = deque(maxlen=100)

def send_sse_message(message):
    """
    Función para agregar un mensaje a la cola.
    """
    sse_message_queue.append(message)


class IsAuthenticatedOrReadOnly(permissions.BasePermission):
    """ Permiso personalizado: permite lectura a todos, pero escritura solo a usuarios autenticados """
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user and request.user.is_authenticated
    

class BacklogUserStoriesView(APIView):
    permission_classes = []

    def get(self, request, project_id):
        try:
            project = Project.objects.get(id=project_id)
        except Project.DoesNotExist:
            return Response({"error": "Proyecto no encontrado"}, status=404)

        # Solo historias sin sprint asignado
        stories = UserStory.objects.filter(project=project, milestone__isnull=True)
        data = [{"id": story.id, "title": story.subject} for story in stories]
        return Response(data)


class PlanningSessionViewSet(viewsets.ModelViewSet):
    queryset = PlanningSession.objects.all()
    serializer_class = PlanningSessionSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        queryset = super().get_queryset()
        project_id = self.request.query_params.get("project")
        if project_id:
            queryset = queryset.filter(project_id=project_id)
        return queryset

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=['get'])
    def estimation_status(self, request, pk=None):
        """
        Devuelve el estado de las estimaciones para una sesión específica
        """
        try:
            session = self.get_object()
            user_story_id = request.query_params.get('user_story')
            
            if not user_story_id:
                return Response({"error": "user_story parameter is required"}, status=400)
            
            # Roles que NO pueden votar
            non_voting_roles = ['Product Owner', 'Scrum Master', 'Stakeholder']
            
            # Obtener todos los miembros del proyecto que pueden votar
            voting_memberships = Membership.objects.filter(
                project=session.project
            ).exclude(
                role__name__in=non_voting_roles
            ).select_related('user', 'role')
            
            total_voters = voting_memberships.count()
            
            # Obtener estimaciones para esta historia
            estimations = Estimation.objects.filter(
                session=session,
                user_story_id=user_story_id
            ).select_related('user')
            
            # Crear mapa de estimaciones
            estimations_map = {}
            for estimation in estimations:
                estimations_map[estimation.user_id] = estimation.estimation_value
            
            voted_count = len(estimations_map)
            missing_votes = max(0, total_voters - voted_count)
            
            # Verificar consenso
            has_consensus = False
            consensus_value = None
            
            if missing_votes == 0 and voted_count > 0:
                unique_values = set(estimations_map.values())
                if len(unique_values) == 1:
                    has_consensus = True
                    consensus_value = list(unique_values)[0]
            
            # Identificar quiénes faltan por votar
            voted_user_ids = set(estimations_map.keys())
            missing_users = []
            for membership in voting_memberships:
                if membership.user_id not in voted_user_ids:
                    missing_users.append({
                        'id': membership.user_id,
                        'full_name': membership.user.get_full_name() or membership.user.username,
                        'role': membership.role.name
                    })
            
            return Response({
                'total_voters': total_voters,
                'voted_count': voted_count,
                'missing_votes': missing_votes,
                'has_consensus': has_consensus,
                'consensus_value': consensus_value,
                'estimations': estimations_map,
                'missing_users': missing_users
            })
            
        except PlanningSession.DoesNotExist:
            return Response({"error": "Session not found"}, status=404)
        except Exception as e:
            print(f"❌ Error en estimation_status: {str(e)}")
            print(traceback.format_exc())
            return Response({"error": "Error interno del servidor"}, status=500)

    @action(detail=True, methods=['get'])
    def export_excel(self, request, pk=None):
        """
        Exporta los datos de una sesión de Planning Poker a Excel
        """
        try:
            session = self.get_object()
            
            # Verificar permisos - en Taiga los permisos funcionan diferente
            # Verificar si el usuario es miembro del proyecto
            membership = Membership.objects.filter(
                project=session.project,
                user=request.user
            ).first()
            
            if not membership:
                return Response(
                    {"error": "No tienes permisos para exportar esta sesión"},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Obtener todas las historias de la sesión
            stories = session.user_stories.all()
            
            # Datos generales de la sesión
            session_data = {
                'ID Sesión': [session.id],
                'Nombre': [session.name],
                'Proyecto': [session.project.name],
                'Estado': ['Activa' if session.is_active else 'Cerrada'],
                'En Discusión': ['Sí' if session.in_discussion else 'No'],
                'Fecha Creación': [session.created_at.strftime('%Y-%m-%d %H:%M') if session.created_at else ''],
            }
            df_session = pd.DataFrame(session_data)
            
            # Datos de las historias y estimaciones
            stories_data = []
            for story in stories:
                # Obtener todas las estimaciones para esta historia
                estimations = Estimation.objects.filter(
                    session=session,
                    user_story=story
                ).select_related('user')
                
                # Calcular consenso
                estimation_values = list(estimations.values_list('estimation_value', flat=True))
                has_consensus = len(set(estimation_values)) == 1 if estimation_values else False
                consensus_value = estimation_values[0] if has_consensus and estimation_values else None
                
                story_dict = {
                    'ID Historia': story.id,
                    'Ref': f"#{story.ref}" if hasattr(story, 'ref') else '',
                    'Título': story.subject,
                    'Total Votantes': estimations.count(),
                    'Tiene Consenso': 'Sí' if has_consensus else 'No',
                    'Valor Consenso': consensus_value if consensus_value else 'N/A',
                    'Estimación Final': story.total_points if hasattr(story, 'total_points') else 'N/A'
                }
                
                # Agregar estimaciones individuales
                for estimation in estimations:
                    col_name = f"Voto - {estimation.user.get_full_name() or estimation.user.username}"
                    story_dict[col_name] = estimation.estimation_value
                
                stories_data.append(story_dict)
            
            df_stories = pd.DataFrame(stories_data) if stories_data else pd.DataFrame()
            
            # Detalle de todas las estimaciones
            all_estimations = Estimation.objects.filter(
                session=session
            ).select_related('user', 'user_story').order_by('user_story', 'created_at')
            
            estimations_data = []
            for est in all_estimations:
                estimations_data.append({
                    'ID': est.id,
                    'Historia': est.user_story.subject,
                    'Usuario': est.user.get_full_name() or est.user.username,
                    'Email': est.user.email,
                    'Rol': self._get_user_role(est.user, session.project),
                    'Valor Estimación': est.estimation_value,
                    'Es Final': 'Sí' if est.final else 'No',
                    'Fecha/Hora': est.created_at.strftime('%Y-%m-%d %H:%M:%S') if est.created_at else ''
                })
            
            df_estimations = pd.DataFrame(estimations_data) if estimations_data else pd.DataFrame()
            
            # Resumen por usuario
            user_summary = []
            participants = Participant.objects.filter(session=session).select_related('user')
            
            for participant in participants:
                user_estimations = Estimation.objects.filter(
                    session=session,
                    user=participant.user
                )
                # Importar models de Django para usar Avg
                from django.db import models
                
                user_summary.append({
                    'Usuario': participant.user.get_full_name() or participant.user.username,
                    'Rol': participant.role or self._get_user_role(participant.user, session.project),
                    'Total Estimaciones': user_estimations.count(),
                    'Historias Votadas': user_estimations.values('user_story').distinct().count(),
                    'Promedio Estimación': user_estimations.aggregate(
                        avg=models.Avg('estimation_value')
                    )['avg'] or 0
                })
            
            df_users = pd.DataFrame(user_summary) if user_summary else pd.DataFrame()
            
            # Crear el archivo Excel
            output = BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                # Escribir cada DataFrame en una hoja diferente
                df_session.to_excel(writer, sheet_name='Información Sesión', index=False)
                
                if not df_stories.empty:
                    df_stories.to_excel(writer, sheet_name='Historias y Consenso', index=False)
                    
                    # Ajustar anchos de columna
                    worksheet = writer.sheets['Historias y Consenso']
                    for idx, col in enumerate(df_stories.columns):
                        max_len = max(
                            df_stories[col].astype(str).map(len).max(),
                            len(col)
                        ) + 2
                        worksheet.set_column(idx, idx, min(max_len, 50))
                
                if not df_estimations.empty:
                    df_estimations.to_excel(writer, sheet_name='Detalle Estimaciones', index=False)
                
                if not df_users.empty:
                    df_users.to_excel(writer, sheet_name='Resumen por Usuario', index=False)
                
                # Agregar formato a las hojas
                workbook = writer.book
                header_format = workbook.add_format({
                    'bold': True,
                    'bg_color': '#4472C4',
                    'font_color': 'white',
                    'border': 1
                })
                
                # Aplicar formato a los encabezados
                for sheet_name in writer.sheets:
                    worksheet = writer.sheets[sheet_name]
                    worksheet.freeze_panes(1, 0)  # Congelar primera fila
            
            # Preparar la respuesta
            output.seek(0)
            filename = f"planning_poker_session_{session.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            
            response = HttpResponse(
                output.read(),
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            
            return response
            
        except Exception as e:
            print(f"Error al exportar Planning Poker: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return Response(
                {"error": f"Error al generar el archivo Excel: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _get_user_role(self, user, project):
        """
        Obtiene el rol del usuario en el proyecto
        """
        try:
            membership = Membership.objects.filter(
                project=project,
                user=user
            ).select_related('role').first()
            
            if membership and membership.role:
                return membership.role.name
            return "Sin rol"
        except Exception as e:
            print(f"Error obteniendo rol: {str(e)}")
            return "Sin rol"
        
class ParticipantViewSet(viewsets.ModelViewSet):
    queryset = Participant.objects.all()
    serializer_class = ParticipantSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
        session_id = self.request.query_params.get("session")
        user_id = self.request.query_params.get("user")

        if session_id:
            queryset = queryset.filter(session_id=session_id)
        if user_id:
            queryset = queryset.filter(user_id=user_id)

        return queryset
    

class EstimationViewSet(viewsets.ModelViewSet):
    queryset = Estimation.objects.all()
    serializer_class = EstimationSerializer

    def get_queryset(self):
        """
        Filtrar estimaciones por sesión, historia y/o usuario
        """
        queryset = super().get_queryset()
        
        session_id = self.request.query_params.get('session')
        user_story_id = self.request.query_params.get('user_story')
        user_id = self.request.query_params.get('user')
        
        # Debug - Corregido para Taiga
        print(f"🔍 Filtrando estimaciones - session: {session_id}, user_story: {user_story_id}, user: {user_id}")
        
        # En Taiga, los roles se obtienen a través de Membership
        try:
            if hasattr(self.request, 'user') and self.request.user.is_authenticated:
                user = self.request.user
                print(f"🔍 Usuario solicitante: {user.username} (ID: {user.id})")
                
                # Si hay un session_id, buscar el rol del usuario en el proyecto de esa sesión
                if session_id:
                    try:
                        session = PlanningSession.objects.get(id=session_id)
                        membership = Membership.objects.filter(
                            project=session.project,
                            user=user
                        ).first()
                        
                        if membership:
                            print(f"🔍 Rol del usuario: {membership.role.name}")
                        else:
                            print(f"🔍 Usuario no es miembro del proyecto")
                    except PlanningSession.DoesNotExist:
                        print(f"❌ Sesión {session_id} no encontrada")
        except Exception as e:
            print(f"⚠️ Error obteniendo información del usuario: {str(e)}")
        
        if session_id:
            queryset = queryset.filter(session_id=session_id)
        if user_story_id:
            queryset = queryset.filter(user_story_id=user_story_id)
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        
        # Debug
        print(f"🔍 Estimaciones encontradas: {queryset.count()}")
        for est in queryset[:5]:  # Solo las primeras 5 para no llenar logs
            print(f"   - Session: {est.session_id}, Story: {est.user_story_id}, User: {est.user_id}, Value: {est.estimation_value}")
            
        return queryset.select_related('user', 'user_story', 'session')

    def list(self, request, *args, **kwargs):
        """
        Override list para incluir información adicional útil
        """
        try:
            queryset = self.filter_queryset(self.get_queryset())
            
            # Si se solicita un formato específico para el frontend
            if request.query_params.get('format') == 'by_user':
                estimations_by_user = {}
                for estimation in queryset:
                    estimations_by_user[estimation.user_id] = {
                        'estimation_value': estimation.estimation_value,
                        'user_name': estimation.user.get_full_name() or estimation.user.username,
                        'created_at': estimation.created_at
                    }
                return Response(estimations_by_user)
            
            # Respuesta estándar
            serializer = self.get_serializer(queryset, many=True)
            return Response(serializer.data)
        except Exception as e:
            print(f"❌ Error en list: {str(e)}")
            print(traceback.format_exc())
            return Response({"error": "Error al listar estimaciones"}, status=500)

    def create(self, request, *args, **kwargs):
        try:
            session_id = request.data.get("session")
            user_story_id = request.data.get("user_story")
            user_id = request.data.get("user")

            print(f"🔍 Recibido - session: {session_id}, user_story: {user_story_id}, user: {user_id}")

            # Validar que los datos existen en la base de datos
            try:
                session = PlanningSession.objects.get(id=session_id)
                user_story = UserStory.objects.get(id=user_story_id)
                user = User.objects.get(id=user_id)
            except PlanningSession.DoesNotExist:
                return Response({"error": "Session no existe"}, status=status.HTTP_404_NOT_FOUND)
            except UserStory.DoesNotExist:
                return Response({"error": "UserStory no existe"}, status=status.HTTP_404_NOT_FOUND)
            except User.DoesNotExist:
                return Response({"error": "User no existe"}, status=status.HTTP_404_NOT_FOUND)

            print("✅ Todos los datos existen en la base de datos")

            # Validar que la historia de usuario pertenece al mismo proyecto de la sesión
            if user_story.project_id != session.project_id:
                print("❌ La historia de usuario no pertenece al proyecto de la sesión.")
                return Response({"error": "La historia de usuario no pertenece al proyecto de esta sesión."}, status=status.HTTP_403_FORBIDDEN)
            
            print("✅ La historia de usuario pertenece al proyecto de la sesión.")

            # Verificar membresía del usuario en el proyecto
            membership = Membership.objects.filter(project=session.project, user=user).first()
            if not membership:
                print("❌ El usuario no es miembro del proyecto.")
                return Response({"error": "El usuario no es miembro del proyecto."}, status=status.HTTP_403_FORBIDDEN)
            
            # Verificar si el rol permite estimar
            non_estimating_roles = ['Product Owner', 'Scrum Master', 'Stakeholder']
            role_name = membership.role.name if membership.role else "Sin rol"
            
            if role_name in non_estimating_roles:
                print(f"❌ Permiso denegado: Rol {role_name} no puede estimar.")
                return Response({"error": f"El rol {role_name} no puede realizar estimaciones."}, status=status.HTTP_403_FORBIDDEN)
            
            print(f"✅ Permiso concedido: Usuario con rol {role_name} puede estimar.")

            # Buscar estimación existente
            existing_estimation = Estimation.objects.filter(session=session, user_story=user_story, user=user).first()

            if existing_estimation:
                print(f"✅ Estimación encontrada. ID: {existing_estimation.id}. Actualizando...")
                serializer = self.get_serializer(existing_estimation, data=request.data, partial=True)
            else:
                print("⚠️ No se encontró una estimación existente. Creando una nueva...")
                serializer = self.get_serializer(data=request.data)

            # Validar y guardar
            serializer.is_valid(raise_exception=True)
            estimation = serializer.save()
            print("✅ Estimación guardada correctamente.")

            # Verificar si todos los miembros que pueden estimar han votado
            estimating_memberships = Membership.objects.filter(
                project=session.project
            ).exclude(
                role__name__in=non_estimating_roles
            )
            total_estimators = estimating_memberships.count()
            
            total_estimations = Estimation.objects.filter(
                session=session, 
                user_story=user_story
            ).values('user').distinct().count()

            print(f"👥 Total miembros que pueden estimar: {total_estimators}, 🗳️ Total Estimaciones: {total_estimations}")

            # Preparar respuesta con información adicional
            response_data = serializer.data
            response_data['voting_status'] = {
                'total_voters': total_estimators,
                'voted_count': total_estimations,
                'missing_votes': max(0, total_estimators - total_estimations),
                'all_voted': total_estimations >= total_estimators
            }

            if total_estimations == total_estimators and total_estimators > 0:
                print("✅ Todos los miembros que pueden estimar han votado. Verificando consenso...")

                estimations_values = list(Estimation.objects.filter(
                    session=session, 
                    user_story=user_story
                ).values_list('estimation_value', flat=True))
                
                if len(set(estimations_values)) == 1:
                    print("✅ Todos los votos son iguales. Hay consenso!")
                    
                    final_estimation = estimations_values[0]
                    response_data['consensus'] = {
                        'has_consensus': True,
                        'consensus_value': final_estimation
                    }
                    
                    # NOTA: En Taiga, los puntos se manejan de forma compleja a través de RolePoints
                    # Por ahora, solo registramos el consenso sin actualizar los puntos de la historia
                    print(f"✅ Consenso alcanzado con valor: {final_estimation}")

                    # Marcar la estimación como final
                    Estimation.objects.filter(
                        session=session, 
                        user_story=user_story
                    ).update(final=True)

                    # Asociar la historia a la sesión si no está ya
                    if user_story not in session.user_stories.all():
                        session.user_stories.add(user_story)
                        session.save()
                        print(f"📌 Historia {user_story.id} asociada a la sesión {session.id}")

                    # Notificación de consenso
                    send_sse_message(f"✅ Consenso alcanzado para historia {user_story.subject}: {final_estimation} puntos")

                else:
                    print("⚠️ No hay consenso. Valores diferentes:", set(estimations_values))
                    response_data['consensus'] = {
                        'has_consensus': False,
                        'different_values': list(set(estimations_values))
                    }
                    # Notificación de falta de consenso
                    send_sse_message(f"⚠️ Sin consenso en historia {user_story.subject}. Valores: {list(set(estimations_values))}")

            # Siempre retornamos Response con información completa
            return Response(response_data, status=status.HTTP_200_OK if existing_estimation else status.HTTP_201_CREATED)
            
        except ValidationError as e:
            print(f"❌ Error de validación: {e}")
            error_detail = e.detail if hasattr(e, 'detail') else str(e)
            return Response({"error": error_detail}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            print(f"❌ Error inesperado en create: {str(e)}")
            print(traceback.format_exc())
            return Response({"error": "Error interno del servidor"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['get'])
    def session_summary(self, request):
        """
        Devuelve un resumen de todas las estimaciones de una sesión
        """
        try:
            session_id = request.query_params.get('session')
            if not session_id:
                return Response({"error": "session parameter is required"}, status=400)
            
            try:
                session = PlanningSession.objects.get(id=session_id)
            except PlanningSession.DoesNotExist:
                return Response({"error": "Session not found"}, status=404)
            
            # Obtener todas las historias de la sesión
            stories = session.user_stories.all()
            
            # Roles que no pueden votar
            non_voting_roles = ['Product Owner', 'Scrum Master', 'Stakeholder']
            
            # Total de votantes
            total_voters = Membership.objects.filter(
                project=session.project
            ).exclude(
                role__name__in=non_voting_roles
            ).count()
            
            summary = []
            for story in stories:
                estimations = Estimation.objects.filter(
                    session=session,
                    user_story=story
                ).values_list('estimation_value', flat=True)
                
                voted_count = len(estimations)
                unique_values = set(estimations)
                has_consensus = len(unique_values) == 1 and voted_count == total_voters
                
                summary.append({
                    'story_id': story.id,
                    'story_subject': story.subject,
                    'total_voters': total_voters,
                    'voted_count': voted_count,
                    'missing_votes': max(0, total_voters - voted_count),
                    'has_consensus': has_consensus,
                    'consensus_value': list(unique_values)[0] if has_consensus else None,
                    'all_values': list(estimations)
                })
            
            return Response(summary)
        except Exception as e:
            print(f"❌ Error en session_summary: {str(e)}")
            print(traceback.format_exc())
            return Response({"error": "Error interno del servidor"}, status=500)
    

class PlanningSessionStatusViewSet(viewsets.ViewSet):
    """
    Vista para obtener el estado de una sesión de Planning Poker
    """

    def retrieve(self, request, pk=None):
        try:
            session = PlanningSession.objects.get(pk=pk)
            serializer = PlanningSessionStatusSerializer(session)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except PlanningSession.DoesNotExist:
            return Response({"error": "La sesión no existe"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            print(f"❌ Error en retrieve: {str(e)}")
            print(traceback.format_exc())
            return Response({"error": "Error interno del servidor"}, status=500)


def event_stream():
    last_sent_index = 0
    while True:
        if len(sse_message_queue) > last_sent_index:
            message = sse_message_queue[last_sent_index]
            yield f"data: {message}\n\n"
            last_sent_index += 1
        time.sleep(1)  


def sse_notifications(request):
    """
    Endpoint SSE para notificaciones de Planning Poker.
    """
    response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    return response


class TeamCapacityView(APIView):
    """
    Calcula la capacidad del equipo, considerando velocidad y factor de foco.
    """

    def post(self, request, *args, **kwargs):
        # Obtener datos del request
        try:
            estimaciones = request.data.get("estimaciones", [])
            miembros = request.data.get("miembros", 0)
            dias_sprint = request.data.get("dias_sprint", 10)
            horas_dia = request.data.get("horas_dia", 6)
            horas_no_productivas = request.data.get("horas_no_productivas", 1)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        if not estimaciones or miembros == 0:
            return Response({"error": "Datos incompletos para el cálculo."}, status=status.HTTP_400_BAD_REQUEST)

        # 1. Velocidad del equipo
        velocidad_equipo = sum(estimaciones)

        # 2. Capacidad total
        capacidad_total = miembros * dias_sprint * horas_dia

        # 3. Tiempo no productivo
        tiempo_no_productivo = miembros * dias_sprint * horas_no_productivas

        # 4. Tiempo efectivo
        tiempo_efectivo = capacidad_total - tiempo_no_productivo

        # 5. Factor de foco
        factor_foco = tiempo_efectivo / capacidad_total if capacidad_total else 0

        # 6. Velocidad ajustada
        velocidad_ajustada = round(velocidad_equipo * factor_foco)

        return Response({
            "velocidad_equipo": velocidad_equipo,
            "capacidad_total": capacidad_total,
            "tiempo_no_productivo": tiempo_no_productivo,
            "tiempo_efectivo": tiempo_efectivo,
            "factor_foco": round(factor_foco, 2),
            "velocidad_ajustada": velocidad_ajustada
        }, status=status.HTTP_200_OK)


class ValidateTeamCapacityView(APIView):
    """
    Calcula la capacidad ajustada del equipo basado en el Sprint Backlog y compara con las estimaciones.
    """

    def post(self, request, *args, **kwargs):
        try:
            sprint_id = request.data.get("sprint_id")
            miembros = int(request.data.get("miembros", 0))
            dias_sprint = int(request.data.get("dias_sprint", 10))
            horas_dia = int(request.data.get("horas_dia", 6))
            horas_no_productivas = int(request.data.get("horas_no_productivas", 1))

            if not sprint_id or miembros == 0:
                return Response({"error": "Faltan datos necesarios"}, status=status.HTTP_400_BAD_REQUEST)

            # 1. Obtener historias del Sprint Backlog ya estimadas (solo final=True)
            final_estimaciones = Estimation.objects.filter(
                user_story__milestone_id=sprint_id,
                final=True
            ).values('user_story').annotate(
                final_estimation=Max('estimation_value')
            )

            estimaciones = [item['final_estimation'] for item in final_estimaciones]

            if not estimaciones:
                return Response({"error": "No hay historias estimadas en el Sprint Backlog."}, status=status.HTTP_400_BAD_REQUEST)

            velocidad_equipo = sum(estimaciones)

            # 2. Calcular capacidad total y factor de foco ajustado
            horas_productivas_por_dia = horas_dia - horas_no_productivas
            capacidad_total = miembros * dias_sprint * horas_productivas_por_dia
            factor_foco = horas_productivas_por_dia / horas_dia if horas_dia else 0
            velocidad_ajustada = round(velocidad_equipo * factor_foco, 2)

            # 3. Verificar si hay sobrecarga
            if velocidad_ajustada < velocidad_equipo:
                diferencia = round(velocidad_equipo - velocidad_ajustada, 2)
                sobrecarga_msg = f"Sí. El equipo tiene una diferencia de {diferencia} puntos, por encima de lo que puede cubrir con su capacidad efectiva."
            else:
                diferencia = 0
                sobrecarga_msg = "No. El equipo tiene capacidad suficiente para cubrir las estimaciones."

            resultado = {
                "sprint_id": sprint_id,
                "estimaciones": estimaciones,
                "velocidad_equipo": velocidad_equipo,
                "capacidad_total": capacidad_total,
                "horas_productivas_por_dia": horas_productivas_por_dia,
                "factor_foco": round(factor_foco, 2),
                "velocidad_ajustada": velocidad_ajustada,
                "sobrecarga": sobrecarga_msg,
                "diferencia": diferencia
            }

            return Response(resultado, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)