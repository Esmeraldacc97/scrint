# sprint_execution/views.py - VERSIÓN LIMPIA

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.http import HttpResponse
from django.db import IntegrityError
from django.db.models import Count, Sum, Q, Avg
from django.utils.timezone import now, localtime
from datetime import date, timedelta
from io import BytesIO
from django.core.cache import cache
from rest_framework.decorators import action


import pandas as pd
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment

from taiga.projects.tasks.models import Task
from taiga.projects.models import TaskStatus, Project, Membership
from taiga.projects.userstories.models import UserStory
from taiga.projects.milestones.models import Milestone
from planning_poker.models import Estimation

from .task_selection import obtener_tareas_por_historia
from .sse import send_sse_message
from .models import (
    SelectedTask, SprintReviewEntry, DailyMeeting, DailyResponse,
    SprintClosure, SprintRetrospective
)
from .serializers import (
    SprintReviewEntrySerializer, DailyMeetingListSerializer,
    DailyMeetingDetailSerializer, DailyMeetingCreateSerializer,
    DailyResponseSerializer, SprintClosureSerializer,
    SprintRetrospectiveSerializer
)

from django.contrib.auth import get_user_model
from .permissions import (
    IsScrumMaster, IsProductOwner, IsProjectMember,
    CanApproveSprintReview, CanManageRetrospective
)
from .utils import (
    SprintMetricsCalculator, ReviewAggregator,
    RetrospectiveVotingManager, SprintNotificationService
)

User = get_user_model()


class TaskSelectionView(APIView):
    """Vista para obtener tareas disponibles para selección"""
    def get(self, request, *args, **kwargs):
        sprint_id = request.query_params.get("sprint_id")
        user_story_id = request.query_params.get("user_story_id")
        assigned_to = request.query_params.get("assigned_to")

        if not sprint_id:
            return Response({"error": "Debes proporcionar un sprint_id"}, status=status.HTTP_400_BAD_REQUEST)

        tareas = obtener_tareas_por_historia(sprint_id)

        # Filtrar por user_story_id si se proporciona
        if user_story_id:
            tareas = [h for h in tareas if str(h["historia_id"]) == str(user_story_id)]

        # Filtrar por assigned_to si se proporciona
        if assigned_to:
            for historia in tareas:
                historia["tareas"] = [
                    t for t in historia["tareas"]
                    if Task.objects.filter(id=t["id"], assigned_to_id=assigned_to).exists()
                ]
            tareas = [h for h in tareas if h["tareas"]]

        return Response(tareas, status=status.HTTP_200_OK)


class TaskSelectionCreateView(APIView):
    """Vista para seleccionar una tarea"""
    def post(self, request, *args, **kwargs):
        data = request.data
        user_story_id = data.get("user_story_id")
        task_id = data.get("task_id")

        if not user_story_id or not task_id:
            return Response(
                {"error": "Faltan user_story_id o task_id"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            if SelectedTask.objects.filter(user_story_id=user_story_id, task_id=task_id).exists():
                return Response(
                    {"message": "La tarea ya había sido seleccionada"},
                    status=status.HTTP_200_OK
                )

            selected = SelectedTask.objects.create(
                user_story_id=user_story_id,
                task_id=task_id
            )

            send_sse_message(
                event='task_selected',
                data={
                    "task_id": task_id,
                    "user_story_id": user_story_id,
                    "message": "Tarea seleccionada"
                }
            )

            return Response(
                {
                    "success": "Tarea seleccionada correctamente",
                    "selected_task_id": selected.id
                },
                status=status.HTTP_201_CREATED
            )

        except IntegrityError:
            return Response(
                {"error": "Error al seleccionar la tarea."},
                status=status.HTTP_400_BAD_REQUEST
            )


class UnselectTaskView(APIView):
    """Vista para deseleccionar una tarea"""
    def delete(self, request, *args, **kwargs):
        task_id = request.data.get("task_id")
        user_story_id = request.data.get("user_story_id")

        if not task_id or not user_story_id:
            return Response({"error": "Faltan task_id o user_story_id"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            selected = SelectedTask.objects.get(task_id=task_id, user_story_id=user_story_id)
            selected.delete()

            send_sse_message(
                event='task_unselected',
                data={
                    "task_id": task_id,
                    "user_story_id": user_story_id,
                    "message": "Tarea desasignada"
                }
            )
            return Response({"message": "Tarea desasignada correctamente"}, status=status.HTTP_200_OK)
        except SelectedTask.DoesNotExist:
            return Response({"error": "La tarea no estaba asignada"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class ResumenTareasSeleccionadasView(APIView):
    """Vista para obtener resumen de tareas seleccionadas"""
    def get(self, request, *args, **kwargs):
        user_id = request.query_params.get("user_id")
        story_id = request.query_params.get("user_story_id")

        tareas = SelectedTask.objects.all()

        if user_id:
            tareas = tareas.filter(task__assigned_to_id=user_id)
        if story_id:
            tareas = tareas.filter(user_story_id=story_id)

        resumen = []
        for tarea in tareas.select_related('task', 'user_story', 'task__assigned_to'):
            resumen.append({
                "tarea_id": tarea.task.id,
                "tarea": tarea.task.subject,
                "historia_id": tarea.user_story.id,
                "historia": tarea.user_story.subject,
                "asignado_a": tarea.task.assigned_to.username if tarea.task.assigned_to else "No asignado"
            })

        return Response(resumen, status=status.HTTP_200_OK)


class BulkSelectTasksView(APIView):
    """Vista para seleccionar múltiples tareas"""
    def post(self, request, *args, **kwargs):
        user_story_id = request.data.get("user_story_id")
        task_ids = request.data.get("task_ids", [])

        if not user_story_id or not task_ids:
            return Response({"error": "Faltan user_story_id o task_ids"}, status=status.HTTP_400_BAD_REQUEST)

        seleccionadas = []
        for task_id in task_ids:
            try:
                selected, created = SelectedTask.objects.get_or_create(
                    user_story_id=user_story_id,
                    task_id=task_id,
                )
                if created:
                    seleccionadas.append(selected.id)
                    send_sse_message(
                        event='task_selected',
                        data={
                            "task_id": task_id,
                            "user_story_id": user_story_id,
                            "message": "Tarea seleccionada (bulk)"
                        }
                    )
            except Exception as e:
                return Response({"error": f"Error al seleccionar tarea {task_id}: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            "success": "Tareas seleccionadas correctamente",
            "selected_task_ids": seleccionadas
        }, status=status.HTTP_201_CREATED)


# DAILY MEETING VIEWS

class DailyMeetingListView(APIView):
    """Vista para listar y crear Daily Meetings"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        project_id = request.query_params.get('project', None)
        if not project_id:
            return Response(
                {"error": "Se requiere el ID del proyecto"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            project = Project.objects.get(pk=project_id)
            membership = Membership.objects.get(project=project, user=request.user)
        except (Project.DoesNotExist, Membership.DoesNotExist):
            return Response(
                {"error": "No tienes permisos para este proyecto"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        queryset = DailyMeeting.objects.filter(project_id=project_id)
        
        sprint_id = request.query_params.get('sprint', None)
        if sprint_id:
            queryset = queryset.filter(sprint_id=sprint_id)
        
        start_date = request.query_params.get('start_date', None)
        end_date = request.query_params.get('end_date', None)
        
        if start_date:
            queryset = queryset.filter(date__gte=start_date)
        if end_date:
            queryset = queryset.filter(date__lte=end_date)
        
        active_only = request.query_params.get('active_only', 'true')
        if active_only.lower() == 'true':
            queryset = queryset.filter(is_active=True)
        
        serializer = DailyMeetingListSerializer(queryset.order_by('-date'), many=True)
        return Response(serializer.data)
    
    def post(self, request):
        """Crear un nuevo Daily Meeting (solo Scrum Master)"""
        project_id = request.data.get('project')
        if not project_id:
            return Response(
                {"error": "Se requiere el ID del proyecto"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            membership = Membership.objects.get(
                project_id=project_id,
                user=request.user
            )
            if membership.role.slug != 'scrum-master':
                return Response(
                    {"error": "Solo el Scrum Master puede crear Daily Meetings"},
                    status=status.HTTP_403_FORBIDDEN
                )
        except Membership.DoesNotExist:
            return Response(
                {"error": "No eres miembro del proyecto"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = DailyMeetingCreateSerializer(data=request.data)
        if serializer.is_valid():
            daily_meeting = serializer.save()
            detail_serializer = DailyMeetingDetailSerializer(daily_meeting)
            return Response(detail_serializer.data, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class DailyMeetingDetailView(APIView):
    """Vista para obtener detalles de un Daily Meeting específico"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request, meeting_id):
        try:
            daily_meeting = DailyMeeting.objects.get(pk=meeting_id)
            membership = Membership.objects.get(
                project=daily_meeting.project,
                user=request.user
            )
        except DailyMeeting.DoesNotExist:
            return Response(
                {"error": "Daily Meeting no encontrado"},
                status=status.HTTP_404_NOT_FOUND
            )
        except Membership.DoesNotExist:
            return Response(
                {"error": "No tienes permisos para ver este Daily Meeting"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = DailyMeetingDetailSerializer(daily_meeting)
        return Response(serializer.data)


class DailyMeetingTodayView(APIView):
    """Obtener o crear el Daily Meeting de hoy"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        project_id = request.query_params.get('project')
        if not project_id:
            return Response(
                {"error": "Se requiere el ID del proyecto"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            project = Project.objects.get(pk=project_id)
            membership = Membership.objects.get(project=project, user=request.user)

            # Debug: imprimir el rol del usuario
            print(f"Usuario: {request.user.username}")
            print(f"Rol: {membership.role.name} (slug: {membership.role.slug})")
            
        except (Project.DoesNotExist, Membership.DoesNotExist):
            return Response(
                {"error": "No tienes permisos para este proyecto"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        today = timezone.now().date()
        
        try:
            daily = DailyMeeting.objects.get(project=project, date=today)
        except DailyMeeting.DoesNotExist:
            if membership.role.slug == 'scrum-master':
                active_sprint = Milestone.objects.filter(
                    project=project,
                    closed=False,
                    estimated_start__lte=today,
                    estimated_finish__gte=today
                ).first()
                
                daily = DailyMeeting.objects.create(
                    project=project,
                    date=today,
                    sprint=active_sprint
                )
            else:
                return Response(
                    {"error": "No hay Daily Meeting para hoy. Contacta al Scrum Master."},
                    status=status.HTTP_404_NOT_FOUND
                )
                
        
        serializer = DailyMeetingDetailSerializer(daily)
        return Response(serializer.data)


class DailyResponseCreateView(APIView):
    """Crear o actualizar respuesta del Daily Meeting"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request, meeting_id):
        print("=== DailyResponseCreateView POST ===")
        print(f"Meeting ID: {meeting_id}")
        print(f"Request data: {request.data}")
        print(f"Request user: {request.user}")
        
        try:
            daily_meeting = DailyMeeting.objects.get(pk=meeting_id)
            membership = Membership.objects.get(
                project=daily_meeting.project,
                user=request.user
            )
            
            print(f"Membership role: {membership.role.slug}")
            
            if membership.role.slug in ['product-owner', 'scrum-master', 'stakeholder']:
                return Response(
                    {"error": f"Los usuarios con rol {membership.role.name} no pueden participar en el Daily"},
                    status=status.HTTP_403_FORBIDDEN
                )
        except DailyMeeting.DoesNotExist:
            return Response(
                {"error": "Daily Meeting no encontrado"},
                status=status.HTTP_404_NOT_FOUND
            )
        except Membership.DoesNotExist:
            return Response(
                {"error": "No eres miembro del proyecto"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Verificar si ya existe una respuesta
        try:
            response = DailyResponse.objects.get(
                meeting=daily_meeting,
                user=request.user
            )
            print("Actualizando respuesta existente")
            serializer = DailyResponseSerializer(
                response,
                data=request.data,
                partial=True,
                context={'request': request}
            )
        except DailyResponse.DoesNotExist:
            print("Creando nueva respuesta")
            data = request.data.copy()
            data['meeting'] = daily_meeting.id
            serializer = DailyResponseSerializer(
                data=data,
                context={'request': request}
            )
        
        if serializer.is_valid():
            print("Serializer válido")
            serializer.save()
            print(f"Respuesta guardada")
            
            # Retornar el daily meeting actualizado
            daily_meeting.refresh_from_db()
            daily_serializer = DailyMeetingDetailSerializer(daily_meeting)
            return Response(daily_serializer.data, status=status.HTTP_201_CREATED)
        else:
            print(f"Errores del serializer: {serializer.errors}")
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class DailyResponseDetailView(APIView):
    """Ver respuesta específica del usuario"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request, meeting_id):
        try:
            daily_meeting = DailyMeeting.objects.get(pk=meeting_id)
            response = DailyResponse.objects.get(
                meeting=daily_meeting,
                user=request.user
            )
            serializer = DailyResponseSerializer(response)
            return Response(serializer.data)
        except DailyMeeting.DoesNotExist:
            return Response(
                {"error": "Daily Meeting no encontrado"},
                status=status.HTTP_404_NOT_FOUND
            )
        except DailyResponse.DoesNotExist:
            return Response(
                {"error": "No has respondido a este Daily Meeting"},
                status=status.HTTP_404_NOT_FOUND
            )


class DailyMeetingExportView(APIView):
    """Exportar Daily Meeting a Excel"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request, meeting_id):
        try:
            daily_meeting = DailyMeeting.objects.get(pk=meeting_id)
            membership = Membership.objects.get(
                project=daily_meeting.project,
                user=request.user
            )
            
            if membership.role.slug != 'scrum-master':
                return Response(
                    {"error": "Solo el Scrum Master puede exportar Daily Meetings"},
                    status=status.HTTP_403_FORBIDDEN
                )
        except DailyMeeting.DoesNotExist:
            return Response(
                {"error": "Daily Meeting no encontrado"},
                status=status.HTTP_404_NOT_FOUND
            )
        except Membership.DoesNotExist:
            return Response(
                {"error": "No eres miembro del proyecto"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = f"Daily Meeting {daily_meeting.date}"
        
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
        center_alignment = Alignment(horizontal="center", vertical="center")
        
        ws['A1'] = "Daily Meeting"
        ws['B1'] = daily_meeting.project.name
        ws['A2'] = "Fecha:"
        ws['B2'] = daily_meeting.date.strftime("%d/%m/%Y")
        ws['A3'] = "Sprint:"
        ws['B3'] = daily_meeting.sprint.name if daily_meeting.sprint else "Sin sprint"
        
        headers = [
            "Miembro del Equipo", "¿Qué hiciste ayer?", 
            "¿Qué harás hoy?", "¿Tienes bloqueadores?", 
            "Estado de ánimo", "Hora de respuesta"
        ]
        
        row = 5
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=row, column=col)
            cell.value = header
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = center_alignment
        
        row = 6
        for response in daily_meeting.responses.all():
            ws.cell(row=row, column=1).value = response.user.get_full_name()
            ws.cell(row=row, column=2).value = response.yesterday_work
            ws.cell(row=row, column=3).value = response.today_plan
            ws.cell(row=row, column=4).value = response.blockers or "No"
            ws.cell(row=row, column=5).value = response.get_mood_display()
            ws.cell(row=row, column=6).value = localtime(response.created_at).strftime("%H:%M")
            row += 1
        
        row += 2
        ws.cell(row=row, column=1).value = "RESUMEN"
        ws.cell(row=row, column=1).font = Font(bold=True)
        
        row += 1
        ws.cell(row=row, column=1).value = "Total de respuestas:"
        ws.cell(row=row, column=2).value = daily_meeting.get_participants_count()
        
        row += 1
        ws.cell(row=row, column=1).value = "Miembros pendientes:"
        ws.cell(row=row, column=2).value = len(daily_meeting.get_pending_members())
        
        pending = daily_meeting.get_pending_members()
        if pending:
            row += 2
            ws.cell(row=row, column=1).value = "Miembros que no han respondido:"
            ws.cell(row=row, column=1).font = Font(bold=True)
            row += 1
            for member in pending:
                ws.cell(row=row, column=1).value = f"- {member.get_full_name()}"
                row += 1
        
        for column in ws.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 50)
            ws.column_dimensions[column_letter].width = adjusted_width
        
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        filename = f"daily_meeting_{daily_meeting.project.slug}_{daily_meeting.date}.xlsx"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        wb.save(response)
        return response


# TASK MANAGEMENT VIEWS

class UpdateTaskStatusView(APIView):
    """Vista para actualizar el estado de una tarea"""
    def patch(self, request, *args, **kwargs):
        task_id = request.data.get("task_id")
        new_status_slug = request.data.get("status")

        if not task_id or not new_status_slug:
            return Response({"error": "task_id y status son requeridos"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            task = Task.objects.get(id=task_id)
            status_obj = TaskStatus.objects.get(slug=new_status_slug, project=task.project)

            task.status = status_obj
            task.save()

            send_sse_message(
                event="task_status_updated",
                data={
                    "task_id": task.id,
                    "new_status": new_status_slug,
                    "message": "Estado de tarea actualizado"
                }
            )

            return Response({"message": "Estado de la tarea actualizado correctamente"}, status=status.HTTP_200_OK)

        except Task.DoesNotExist:
            return Response({"error": "Tarea no encontrada"}, status=status.HTTP_404_NOT_FOUND)
        except TaskStatus.DoesNotExist:
            return Response({"error": "Estado no válido para el proyecto"}, status=status.HTTP_400_BAD_REQUEST)


class TaskStatusSummaryView(APIView):
    """Vista para obtener resumen de estados de tareas"""
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        sprint_id = request.query_params.get('sprint_id')

        if not sprint_id:
            return Response({"error": "Se requiere el parámetro sprint_id"}, status=400)

        status_counts = (
            Task.objects.filter(milestone_id=sprint_id)
            .values("status__slug")
            .annotate(count=Count("id"))
        )

        resumen = {item["status__slug"]: item["count"] for item in status_counts}
        return Response(resumen, status=200)


# SPRINT METRICS VIEWS

class BurndownChartView(APIView):
    """Vista para obtener datos del burndown chart"""
    def get(self, request, *args, **kwargs):
        sprint_id = request.query_params.get("sprint_id")
        if not sprint_id:
            return Response({"error": "sprint_id es requerido"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            sprint = Milestone.objects.get(id=sprint_id)
        except Milestone.DoesNotExist:
            return Response({"error": "Sprint no encontrado"}, status=status.HTTP_404_NOT_FOUND)

        start_date = sprint.estimated_start
        end_date = sprint.estimated_finish
        total_days = (end_date - start_date).days + 1

        total_tasks = Task.objects.filter(milestone_id=sprint_id).count()
        ideal_line = []
        real_line = []
        
        for day in range(total_days):
            current_date = start_date + timedelta(days=day)
            remaining_ideal = total_tasks - int((total_tasks / total_days) * day)
            ideal_line.append({
                "day": current_date.strftime("%Y-%m-%d"), 
                "remaining_tasks": remaining_ideal
            })
            
            closed_tasks = Task.objects.filter(
                milestone_id=sprint_id,
                status__slug="closed",
                modified_date__date__lte=current_date
            ).count()
            remaining_real = total_tasks - closed_tasks
            real_line.append({
                "day": current_date.strftime("%Y-%m-%d"), 
                "remaining_tasks": remaining_real
            })

        return Response({
            "ideal": ideal_line,
            "real": real_line,
            "total_tasks": total_tasks
        }, status=status.HTTP_200_OK)


class TeamVelocityView(APIView):
    """Vista para obtener la velocidad del equipo"""
    def get(self, request, *args, **kwargs):
        sprint_id = request.query_params.get("sprint_id")
        if not sprint_id:
            return Response({"error": "sprint_id es requerido"}, status=status.HTTP_400_BAD_REQUEST)

        estimaciones = Estimation.objects.filter(
            final=True,
            user_story__milestone_id=sprint_id
        )

        velocidad_total = estimaciones.aggregate(total=Sum("estimation_value"))["total"] or 0

        return Response({
            "sprint_id": sprint_id,
            "velocidad_total": velocidad_total
        }, status=status.HTTP_200_OK)


class SprintRemainingDaysView(APIView):
    """Vista para obtener días restantes del sprint"""
    def get(self, request, *args, **kwargs):
        sprint_id = request.query_params.get("sprint_id")
        if not sprint_id:
            return Response({"error": "sprint_id es requerido"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            sprint = Milestone.objects.get(id=sprint_id)
        except Milestone.DoesNotExist:
            return Response({"error": "Sprint no encontrado"}, status=status.HTTP_404_NOT_FOUND)

        today = date.today()
        start_date = sprint.estimated_start
        end_date = sprint.estimated_finish

        if today < start_date:
            estado = "no iniciado"
            dias_restantes = (end_date - start_date).days + 1
        elif today > end_date:
            estado = "finalizado"
            dias_restantes = 0
        else:
            estado = "en curso"
            dias_restantes = (end_date - today).days + 1

        return Response({
            "sprint_id": sprint_id,
            "sprint_nombre": sprint.name,
            "estado": estado,
            "dias_restantes": dias_restantes
        }, status=status.HTTP_200_OK)


class SprintSummaryView(APIView):
    """Vista para obtener resumen del sprint"""
    def get(self, request, *args, **kwargs):
        sprint_id = request.query_params.get("sprint_id")
        if not sprint_id:
            return Response({"error": "sprint_id es requerido"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            sprint = Milestone.objects.get(id=sprint_id)
        except Milestone.DoesNotExist:
            return Response({"error": "Sprint no encontrado"}, status=status.HTTP_404_NOT_FOUND)

        today = date.today()
        start = sprint.estimated_start
        end = sprint.estimated_finish

        if today < start:
            estado = "no iniciado"
        elif today > end:
            estado = "finalizado"
        else:
            estado = "en curso"

        dias_restantes = max((end - today).days, 0)

        total_tasks = Task.objects.filter(milestone_id=sprint_id).count()
        tasks_closed = Task.objects.filter(milestone_id=sprint_id, status__slug="closed").count()
        avance_porcentaje = (tasks_closed / total_tasks) * 100 if total_tasks > 0 else 0

        return Response({
            "sprint_id": str(sprint.id),
            "sprint_name": sprint.name,
            "start_date": sprint.estimated_start,
            "end_date": sprint.estimated_finish,
            "dias_restantes": dias_restantes,
            "estado": estado,
            "total_tasks": total_tasks,
            "tasks_closed": tasks_closed,
            "avance_porcentaje": round(avance_porcentaje, 2),
            "metricas_links": {
                "burndown_chart": f"/api/v1/burndown-chart/?sprint_id={sprint.id}",
                "team_velocity": f"/api/v1/team-velocity/?sprint_id={sprint.id}",
                "task_status_summary": f"/api/v1/task-status-summary/?sprint_id={sprint.id}",
                "daily_meetings": f"/api/v1/daily-meetings/?sprint={sprint.id}",
                "planning_poker_estimations": f"/api/v1/planning-poker/estimations/?sprint_id={sprint.id}",
                "selected_tasks": f"/api/v1/selected-tasks/?sprint_id={sprint.id}"
            }
        }, status=status.HTTP_200_OK)


class SprintSummaryExportView(APIView):
    """Vista para exportar resumen del sprint a Excel"""
    def get(self, request, *args, **kwargs):
        sprint_id = request.query_params.get("sprint_id")
        if not sprint_id:
            return Response({"error": "sprint_id es requerido"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            sprint = Milestone.objects.get(id=sprint_id)
        except Milestone.DoesNotExist:
            return Response({"error": "Sprint no encontrado"}, status=status.HTTP_404_NOT_FOUND)

        today = date.today()
        start = sprint.estimated_start
        end = sprint.estimated_finish

        estado = "en curso"
        if today < start:
            estado = "no iniciado"
        elif today > end:
            estado = "finalizado"

        dias_restantes = max((end - today).days, 0)
        total_tasks = Task.objects.filter(milestone_id=sprint_id).count()
        tasks_closed = Task.objects.filter(milestone_id=sprint_id, status__slug="closed").count()
        avance_porcentaje = (tasks_closed / total_tasks) * 100 if total_tasks > 0 else 0

        # Resumen General
        resumen_data = {
            "sprint_id": [sprint.id],
            "sprint_name": [sprint.name],
            "start_date": [sprint.estimated_start],
            "end_date": [sprint.estimated_finish],
            "dias_restantes": [dias_restantes],
            "estado": [estado],
            "total_tasks": [total_tasks],
            "tasks_closed": [tasks_closed],
            "avance_porcentaje": [round(avance_porcentaje, 2)]
        }
        df_summary = pd.DataFrame(resumen_data)

        # Estimaciones Planning Poker
        estimaciones = Estimation.objects.filter(user_story__milestone_id=sprint_id).select_related("user_story", "user")
        df_estimaciones = pd.DataFrame([{
            "id": e.id,
            "user_story_id": e.user_story.id,
            "user_story_name": e.user_story.subject,
            "user_id": e.user.id,
            "username": e.user.username,
            "estimation_value": e.estimation_value,
            "final": e.final,
            "created_at": e.created_at.replace(tzinfo=None) if e.created_at else None
        } for e in estimaciones])

        # Tareas seleccionadas
        seleccionadas = SelectedTask.objects.filter(task__milestone_id=sprint_id).select_related("task", "user_story")
        df_seleccionadas = pd.DataFrame([{
            "id": s.id,
            "task_id": s.task.id,
            "task_name": s.task.subject,
            "user_story_id": s.user_story.id,
            "user_story_name": s.user_story.subject,
            "selected_at": s.selected_at.replace(tzinfo=None) if s.selected_at else None
        } for s in seleccionadas])

        # Daily Meetings
        daily_meetings = DailyMeeting.objects.filter(sprint_id=sprint_id)
        daily_data = []
        for meeting in daily_meetings:
            for response in meeting.responses.all():
                daily_data.append({
                    "date": meeting.date,
                    "user": response.user.username,
                    "yesterday_work": response.yesterday_work,
                    "today_plan": response.today_plan,
                    "blockers": response.blockers or "No",
                    "mood": response.get_mood_display()
                })
        df_daily = pd.DataFrame(daily_data)

        # Exportar a Excel
        output = BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            df_summary.to_excel(writer, index=False, sheet_name="Resumen")
            if not df_estimaciones.empty:
                df_estimaciones.to_excel(writer, index=False, sheet_name="Estimaciones")
            if not df_seleccionadas.empty:
                df_seleccionadas.to_excel(writer, index=False, sheet_name="Tareas Seleccionadas")
            if not df_daily.empty:
                df_daily.to_excel(writer, index=False, sheet_name="Daily Meetings")

        output.seek(0)
        response = HttpResponse(output.read(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response["Content-Disposition"] = f'attachment; filename=Sprint_{sprint.id}_Resumen.xlsx'
        return response


# SPRINT CEREMONIES VIEWS

class SprintReviewView(APIView):
    """API para gestionar el Sprint Review"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Obtiene el estado del Review para un sprint"""
        sprint_id = request.query_params.get('sprint_id')
        
        if not sprint_id:
            return Response(
                {"error": "sprint_id es requerido"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            sprint = Milestone.objects.get(id=sprint_id)
            
            # Verificar permisos
            if not request.user.has_perm('view_sprint', sprint):
                return Response(
                    {"error": "Sin permisos para ver este sprint"},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Obtener historias completadas
            completed_stories = sprint.user_stories.filter(
                is_closed=True
            ).values('id', 'subject', 'points', 'description')
            
            # Obtener feedback existente
            existing_feedback = SprintReviewEntry.objects.filter(
                sprint=sprint,
                user=request.user
            ).first()
            
            # Obtener métricas del sprint
            total_points = sprint.user_stories.aggregate(
                total=Sum('points')
            )['total'] or 0
            
            completed_points = sprint.user_stories.filter(
                is_closed=True
            ).aggregate(total=Sum('points'))['total'] or 0
            
            response_data = {
                'sprint': {
                    'id': sprint.id,
                    'name': sprint.name,
                    'start_date': sprint.estimated_start,
                    'end_date': sprint.estimated_finish
                },
                'completed_stories': list(completed_stories),
                'metrics': {
                    'total_points': total_points,
                    'completed_points': completed_points,
                    'completion_rate': (completed_points/total_points*100) if total_points > 0 else 0
                },
                'existing_feedback': SprintReviewEntrySerializer(existing_feedback).data if existing_feedback else None,
                'can_approve': request.user.has_perm('approve_sprint', sprint)
            }
            
            return Response(response_data)
            
        except Milestone.DoesNotExist:
            return Response(
                {"error": "Sprint no encontrado"},
                status=status.HTTP_404_NOT_FOUND
            )
    
    def post(self, request):
        """Registra o actualiza feedback del Review"""
        sprint_id = request.data.get('sprint_id')
        
        try:
            sprint = Milestone.objects.get(id=sprint_id)
            
            # Validar que el sprint esté en estado de review
            if not sprint.is_closed:
                return Response(
                    {"error": "El sprint debe estar cerrado para hacer review"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Crear o actualizar feedback
            review_entry, created = SprintReviewEntry.objects.update_or_create(
                sprint=sprint,
                user=request.user,
                defaults={
                    'general_feedback': request.data.get('general_feedback'),
                    'satisfaction_level': request.data.get('satisfaction_level'),
                    'completed_stories_feedback': request.data.get('stories_feedback', {}),
                    'sprint_approved': request.data.get('sprint_approved', False),
                    'requires_changes': request.data.get('requires_changes'),
                    'code_quality_rating': request.data.get('code_quality_rating'),
                    'functionality_rating': request.data.get('functionality_rating')
                }
            )
            
            # Enviar notificación SSE
            send_sse_message(
                f"project_{sprint.project.id}",
                {
                    "type": "sprint_review_updated",
                    "sprint_id": sprint.id,
                    "user": request.user.username,
                    "approved": review_entry.sprint_approved
                }
            )
            
            serializer = SprintReviewEntrySerializer(review_entry)
            return Response(
                serializer.data,
                status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
            )
            
        except Milestone.DoesNotExist:
            return Response(
                {"error": "Sprint no encontrado"},
                status=status.HTTP_404_NOT_FOUND
            )


class SprintClosureView(APIView):
    """Vista para cierre de Sprint"""
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = SprintClosureSerializer(data=request.data, context={"request": request})
        if serializer.is_valid():
            closure = serializer.save()
            return Response(SprintClosureSerializer(closure).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get(self, request, *args, **kwargs):
        sprint_id = request.query_params.get("sprint_id")
        if not sprint_id:
            return Response({"error": "sprint_id es requerido"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            closure = SprintClosure.objects.get(sprint_id=sprint_id)
            serializer = SprintClosureSerializer(closure)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except SprintClosure.DoesNotExist:
            return Response({"error": "Este sprint no ha sido cerrado"}, status=status.HTTP_404_NOT_FOUND)


class SprintRetrospectiveView(APIView):
    """API mejorada para gestionar la Retrospectiva del Sprint"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Obtiene la retrospectiva de un sprint con votación"""
        sprint_id = request.query_params.get('sprint_id')
        
        if not sprint_id:
            return Response(
                {"error": "sprint_id es requerido"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            sprint = Milestone.objects.get(id=sprint_id)
            
            # Verificar permisos
            try:
                membership = Membership.objects.get(
                    project=sprint.project,
                    user=request.user
                )
            except Membership.DoesNotExist:
                return Response(
                    {"error": "No eres miembro del proyecto"},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Intentar obtener retrospectiva existente
            try:
                retrospective = sprint.retrospective
                
                # Agregar votos desde caché a los items
                for idx, item in enumerate(retrospective.went_well):
                    cache_key = f"retro_vote_{sprint_id}_went_well_{idx}"
                    item['votes'] = cache.get(cache_key, 0)
                
                for idx, item in enumerate(retrospective.to_improve):
                    cache_key = f"retro_vote_{sprint_id}_to_improve_{idx}"
                    item['votes'] = cache.get(cache_key, 0)
                
            except SprintRetrospective.DoesNotExist:
                retrospective = None
            
            # Obtener información del equipo
            team_members = Membership.objects.filter(
                project=sprint.project
            ).exclude(
                role__slug__in=['stakeholder']  # Excluir stakeholders
            ).select_related('user').values(
                'user__id', 'user__username', 'user__full_name',
                'role__name', 'role__slug'
            )
            
            # Obtener acciones previas
            previous_actions = self._get_previous_actions(sprint.project, sprint.id)
            
            # Verificar si es Scrum Master
            is_scrum_master = membership.role.slug == 'scrum-master'
            
            response_data = {
                'sprint': {
                    'id': sprint.id,
                    'name': sprint.name,
                    'project_name': sprint.project.name
                },
                'retrospective': SprintRetrospectiveSerializer(retrospective).data if retrospective else None,
                'team_members': list(team_members),
                'previous_actions': previous_actions,
                'is_scrum_master': is_scrum_master,
                'user_role': membership.role.slug
            }
            
            return Response(response_data)
            
        except Milestone.DoesNotExist:
            return Response(
                {"error": "Sprint no encontrado"},
                status=status.HTTP_404_NOT_FOUND
            )
    
    def post(self, request):
        """Crea o actualiza la retrospectiva"""
        sprint_id = request.data.get('sprint_id')
        
        if not sprint_id:
            return Response(
                {"error": "sprint_id es requerido"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            sprint = Milestone.objects.get(id=sprint_id)
            
            # Verificar permisos (solo Scrum Master)
            try:
                membership = Membership.objects.get(
                    project=sprint.project,
                    user=request.user
                )
                
                if membership.role.slug != 'scrum-master':
                    return Response(
                        {"error": "Solo el Scrum Master puede gestionar retrospectivas"},
                        status=status.HTTP_403_FORBIDDEN
                    )
            except Membership.DoesNotExist:
                return Response(
                    {"error": "No eres miembro del proyecto"},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Calcular velocidad del sprint
            velocity = self._calculate_velocity(sprint)
            
            # Preparar datos
            retro_data = {
                'created_by': request.user,
                'went_well': request.data.get('went_well', []),
                'to_improve': request.data.get('to_improve', []),
                'action_items': request.data.get('action_items', []),
                'team_mood': request.data.get('team_mood', 'neutral'),
                'velocity_achieved': velocity,
                'previous_actions_completed': request.data.get('previous_actions_completed', [])
            }
            
            retrospective, created = SprintRetrospective.objects.update_or_create(
                sprint=sprint,
                defaults=retro_data
            )
            
            # Calcular precisión del compromiso
            retrospective.calculate_commitment_accuracy()
            
            # Limpiar caché de votos si se está actualizando
            if not created:
                self._clear_voting_cache(sprint_id)
            
            # Notificar al equipo
            send_sse_message(
                event='retrospective_updated',
                data={
                    "project_id": sprint.project.id,
                    "sprint_id": sprint.id,
                    "team_mood": retrospective.team_mood,
                    "velocity": velocity,
                    "accuracy": float(retrospective.commitment_accuracy) if retrospective.commitment_accuracy else 0,
                    "action": "created" if created else "updated"
                }
            )
            
            serializer = SprintRetrospectiveSerializer(retrospective)
            return Response(
                serializer.data,
                status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
            )
            
        except Milestone.DoesNotExist:
            return Response(
                {"error": "Sprint no encontrado"},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {"error": f"Error al guardar retrospectiva: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _calculate_velocity(self, sprint):
        """Calcula la velocidad alcanzada en el sprint"""
        return sprint.user_stories.filter(
            is_closed=True
        ).aggregate(total=Sum('points'))['total'] or 0
    
    def _get_previous_actions(self, project, current_sprint_id=None):
        """Obtiene acciones de retrospectivas anteriores"""
        query = SprintRetrospective.objects.filter(
            sprint__project=project
        )
        
        if current_sprint_id:
            query = query.exclude(sprint_id=current_sprint_id)
        
        previous_retrospectives = query.order_by('-created_at')[:3]
        
        actions = []
        for retro in previous_retrospectives:
            for action in retro.action_items:
                # Obtener información del responsable
                responsible_name = "No asignado"
                if action.get('responsible_id'):
                    try:
                        user = User.objects.get(id=action['responsible_id'])
                        responsible_name = user.get_full_name() or user.username
                    except User.DoesNotExist:
                        pass
                
                actions.append({
                    'sprint': retro.sprint.name,
                    'sprint_id': retro.sprint.id,
                    'action': action.get('action'),
                    'responsible_id': action.get('responsible_id'),
                    'responsible_name': responsible_name,
                    'due_date': action.get('due_date'),
                    'completed': action.get('completed', False)
                })
        
        return actions
    
    def _clear_voting_cache(self, sprint_id):
        """Limpia el caché de votación para un sprint"""
        # Obtener todas las claves relacionadas con este sprint
        # Nota: En producción, considera usar Redis con pattern matching
        cache_pattern = f"retro_vote_{sprint_id}_*"
        # Django cache no soporta pattern matching, así que necesitarías
        # mantener un registro de las claves o usar Redis directamente


class SprintExportView(APIView):
    """Vista para exportar Sprint completo"""
    def get(self, request, *args, **kwargs):
        sprint_id = request.query_params.get("sprint_id")
        if not sprint_id:
            return Response({"error": "sprint_id es requerido"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            sprint = Milestone.objects.get(id=sprint_id)
        except Milestone.DoesNotExist:
            return Response({"error": "Sprint no encontrado"}, status=status.HTTP_404_NOT_FOUND)

        # Resumen general
        resumen_data = {
            "sprint_id": [sprint.id],
            "sprint_name": [sprint.name],
            "project_name": [sprint.project.name],
            "start_date": [sprint.estimated_start],
            "end_date": [sprint.estimated_finish],
        }
        df_resumen = pd.DataFrame(resumen_data)

        # Estimaciones
        estimaciones = Estimation.objects.filter(user_story__milestone_id=sprint_id).values(
            "id", "user_story__subject", "user__username", "estimation_value", "final", "created_at"
        )
        df_estimaciones = pd.DataFrame(estimaciones)
        if not df_estimaciones.empty and "created_at" in df_estimaciones.columns:
            df_estimaciones["created_at"] = pd.to_datetime(df_estimaciones["created_at"]).dt.tz_localize(None)

        # Tareas seleccionadas
        seleccionadas = SelectedTask.objects.filter(task__milestone_id=sprint_id).values(
            "id", "task__subject", "user_story__subject", "selected_at"
        )
        df_seleccionadas = pd.DataFrame(seleccionadas)
        if not df_seleccionadas.empty and "selected_at" in df_seleccionadas.columns:
            df_seleccionadas["selected_at"] = pd.to_datetime(df_seleccionadas["selected_at"]).dt.tz_localize(None)

        # Daily Meetings
        daily_meetings = DailyMeeting.objects.filter(sprint_id=sprint_id)
        daily_data = []
        for meeting in daily_meetings:
            for response in meeting.responses.all():
                daily_data.append({
                    "date": meeting.date,
                    "user": response.user.username,
                    "yesterday_work": response.yesterday_work,
                    "today_plan": response.today_plan,
                    "blockers": response.blockers or "No",
                    "mood": response.get_mood_display()
                })
        df_daily = pd.DataFrame(daily_data)

        # Cierre del Sprint
        cierre = SprintClosure.objects.filter(sprint_id=sprint_id).first()
        cierre_data = []
        if cierre:
            cierre_data.append({
                "notes": cierre.notes,
                "closed_at": localtime(cierre.closed_at).replace(tzinfo=None),
                "closed_by": cierre.closed_by.username,
                "sprint_name": cierre.sprint.name,
                "project_name": cierre.sprint.project.name
            })
        df_cierre = pd.DataFrame(cierre_data)

        # Retrospectiva
        retrospectiva = SprintRetrospective.objects.filter(sprint_id=sprint_id).values(
            "positives", "improvements", "actions", "created_at"
        )
        df_retrospectiva = pd.DataFrame(retrospectiva)
        if not df_retrospectiva.empty and "created_at" in df_retrospectiva.columns:
            df_retrospectiva.rename(columns={
                "positives": "Lo bueno",
                "improvements": "A mejorar",
                "actions": "Acciones",
                "created_at": "Fecha de creación"
            }, inplace=True)
            df_retrospectiva["Fecha de creación"] = pd.to_datetime(df_retrospectiva["Fecha de creación"]).dt.tz_localize(None)

        # Exportar
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_resumen.to_excel(writer, index=False, sheet_name="Resumen")
            if not df_estimaciones.empty:
                df_estimaciones.to_excel(writer, index=False, sheet_name="Estimaciones")
            if not df_seleccionadas.empty:
                df_seleccionadas.to_excel(writer, index=False, sheet_name="Tareas Seleccionadas")
            if not df_daily.empty:
                df_daily.to_excel(writer, index=False, sheet_name="Daily Meetings")
            if not df_cierre.empty:
                df_cierre.to_excel(writer, index=False, sheet_name="Cierre Sprint")
            if not df_retrospectiva.empty:
                df_retrospectiva.to_excel(writer, index=False, sheet_name="Retrospectiva")

        output.seek(0)
        filename = f"Sprint_{sprint.id}_ResumenCompleto.xlsx"
        response = HttpResponse(output.read(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response["Content-Disposition"] = f"attachment; filename={filename}"
        return response


class RetrospectiveVoteView(APIView):
    """API mejorada para votación anónima en retrospectivas"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        """Registra un voto anónimo"""
        sprint_id = request.data.get('sprint_id')
        item_type = request.data.get('item_type')  # 'went_well' o 'to_improve'
        item_index = request.data.get('item_index')
        
        # Validaciones
        if not all([sprint_id, item_type, item_index is not None]):
            return Response(
                {"error": "sprint_id, item_type e item_index son requeridos"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if item_type not in ['went_well', 'to_improve']:
            return Response(
                {"error": "item_type debe ser 'went_well' o 'to_improve'"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Verificar que el sprint existe y el usuario es miembro
            sprint = Milestone.objects.get(id=sprint_id)
            membership = Membership.objects.get(
                project=sprint.project,
                user=request.user
            )
        except Milestone.DoesNotExist:
            return Response(
                {"error": "Sprint no encontrado"},
                status=status.HTTP_404_NOT_FOUND
            )
        except Membership.DoesNotExist:
            return Response(
                {"error": "No eres miembro del proyecto"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Verificar que existe la retrospectiva
        try:
            retrospective = sprint.retrospective
            
            # Verificar que el índice es válido
            items = getattr(retrospective, item_type)
            if item_index >= len(items):
                return Response(
                    {"error": "Índice de item inválido"},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except SprintRetrospective.DoesNotExist:
            return Response(
                {"error": "No existe retrospectiva para este sprint"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Claves de caché
        cache_key = f"retro_vote_{sprint_id}_{item_type}_{item_index}"
        user_vote_key = f"user_voted_{sprint_id}_{request.user.id}_{item_type}_{item_index}"
        
        # Verificar si ya votó
        if cache.get(user_vote_key):
            return Response(
                {"error": "Ya has votado por este item"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Incrementar contador de votos
        current_votes = cache.get(cache_key, 0)
        new_votes = current_votes + 1
        cache.set(cache_key, new_votes, timeout=86400)  # 24 horas
        cache.set(user_vote_key, True, timeout=86400)
        
        # Notificar actualización vía SSE
        send_sse_message(
            event='retrospective_vote_updated',
            data={
                "sprint_id": sprint_id,
                "item_type": item_type,
                "item_index": item_index,
                "votes": new_votes
            }
        )
        
        return Response({
            "votes": new_votes,
            "message": "Voto registrado exitosamente"
        })
    
    def get(self, request):
        """Obtiene el estado actual de votos para un item"""
        sprint_id = request.query_params.get('sprint_id')
        item_type = request.query_params.get('item_type')
        item_index = request.query_params.get('item_index')
        
        if not all([sprint_id, item_type, item_index]):
            return Response(
                {"error": "sprint_id, item_type e item_index son requeridos"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        cache_key = f"retro_vote_{sprint_id}_{item_type}_{item_index}"
        votes = cache.get(cache_key, 0)
        
        # Verificar si el usuario ya votó
        user_vote_key = f"user_voted_{sprint_id}_{request.user.id}_{item_type}_{item_index}"
        has_voted = bool(cache.get(user_vote_key))
        
        return Response({
            "votes": votes,
            "has_voted": has_voted
        })


class SprintReviewEntryView(APIView):
    """API mejorada para gestionar el Sprint Review"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Obtiene el estado del Review para un sprint con datos completos"""
        sprint_id = request.query_params.get('sprint_id')
        
        if not sprint_id:
            return Response(
                {"error": "sprint_id es requerido"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            sprint = Milestone.objects.get(id=sprint_id)
            
            # Verificar permisos - verificar si el usuario es miembro del proyecto
            try:
                membership = Membership.objects.get(
                    project=sprint.project,
                    user=request.user
                )
            except Membership.DoesNotExist:
                return Response(
                    {"error": "No tienes permisos para ver este sprint"},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Obtener historias completadas con más detalles
            completed_stories = sprint.user_stories.filter(
                is_closed=True
            ).select_related('owner').values(
                'id', 'subject', 'points', 'description',
                'owner__username', 'owner__full_name'
            )
            
            # Obtener feedback existente del usuario actual
            existing_feedback = SprintReviewEntry.objects.filter(
                sprint=sprint,
                user=request.user
            ).first()
            
            # Obtener todos los feedbacks para calcular métricas agregadas
            all_feedbacks = SprintReviewEntry.objects.filter(sprint=sprint)
            
            # Calcular métricas agregadas
            avg_satisfaction = all_feedbacks.aggregate(
                avg=Avg('satisfaction_level')
            )['avg'] or 0
            
            avg_code_quality = all_feedbacks.exclude(
                code_quality_rating__isnull=True
            ).aggregate(avg=Avg('code_quality_rating'))['avg'] or 0
            
            avg_functionality = all_feedbacks.exclude(
                functionality_rating__isnull=True
            ).aggregate(avg=Avg('functionality_rating'))['avg'] or 0
            
            # Obtener métricas del sprint
            total_points = sprint.user_stories.aggregate(
                total=Sum('points')
            )['total'] or 0
            
            completed_points = sprint.user_stories.filter(
                is_closed=True
            ).aggregate(total=Sum('points'))['total'] or 0
            
            # Verificar si el usuario puede aprobar (es Product Owner)
            can_approve = membership.role.slug == 'product-owner'
            
            # Obtener el número de aprobaciones
            approvals_count = all_feedbacks.filter(sprint_approved=True).count()
            total_feedbacks = all_feedbacks.count()
            
            response_data = {
                'sprint': {
                    'id': sprint.id,
                    'name': sprint.name,
                    'start_date': sprint.estimated_start,
                    'end_date': sprint.estimated_finish,
                    'project_name': sprint.project.name
                },
                'completed_stories': list(completed_stories),
                'metrics': {
                    'total_points': total_points,
                    'completed_points': completed_points,
                    'completion_rate': round((completed_points/total_points*100), 2) if total_points > 0 else 0,
                    'avg_satisfaction': round(avg_satisfaction, 2),
                    'avg_code_quality': round(avg_code_quality, 2),
                    'avg_functionality': round(avg_functionality, 2),
                    'approvals_count': approvals_count,
                    'total_feedbacks': total_feedbacks
                },
                'existing_feedback': SprintReviewEntrySerializer(existing_feedback).data if existing_feedback else None,
                'can_approve': can_approve,
                'user_role': membership.role.slug
            }
            
            return Response(response_data)
            
        except Milestone.DoesNotExist:
            return Response(
                {"error": "Sprint no encontrado"},
                status=status.HTTP_404_NOT_FOUND
            )
    
    def post(self, request):
        """Registra o actualiza feedback del Review"""
        sprint_id = request.data.get('sprint_id')
        
        if not sprint_id:
            return Response(
                {"error": "sprint_id es requerido"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            sprint = Milestone.objects.get(id=sprint_id)
            
            # Verificar que el usuario sea miembro del proyecto
            try:
                membership = Membership.objects.get(
                    project=sprint.project,
                    user=request.user
                )
            except Membership.DoesNotExist:
                return Response(
                    {"error": "No eres miembro del proyecto"},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Validar que el sprint esté cerrado o en revisión
            today = timezone.now().date()
            if today < sprint.estimated_finish:
                return Response(
                    {"error": "El sprint aún no ha terminado"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Preparar datos para guardar
            feedback_data = {
                'general_feedback': request.data.get('general_feedback', ''),
                'satisfaction_level': request.data.get('satisfaction_level', 3),
                'completed_stories_feedback': request.data.get('stories_feedback', {}),
                'code_quality_rating': request.data.get('code_quality_rating'),
                'functionality_rating': request.data.get('functionality_rating')
            }
            
            # Solo el Product Owner puede aprobar el sprint
            if membership.role.slug == 'product-owner':
                feedback_data['sprint_approved'] = request.data.get('sprint_approved', False)
                feedback_data['requires_changes'] = request.data.get('requires_changes', '')
            
            # Crear o actualizar feedback
            review_entry, created = SprintReviewEntry.objects.update_or_create(
                sprint=sprint,
                user=request.user,
                defaults=feedback_data
            )
            
            # Enviar notificación SSE
            send_sse_message(
                event='sprint_review_updated',
                data={
                    "project_id": sprint.project.id,
                    "sprint_id": sprint.id,
                    "user": request.user.username,
                    "user_full_name": request.user.get_full_name(),
                    "approved": review_entry.sprint_approved,
                    "action": "created" if created else "updated"
                }
            )
            
            serializer = SprintReviewEntrySerializer(review_entry)
            return Response(
                serializer.data,
                status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
            )
            
        except Milestone.DoesNotExist:
            return Response(
                {"error": "Sprint no encontrado"},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {"error": f"Error al guardar review: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class SprintReviewExportView(APIView):
    """Exportar Sprint Review a Excel"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        sprint_id = request.query_params.get('sprint_id')
        
        if not sprint_id:
            return Response(
                {"error": "sprint_id es requerido"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            sprint = Milestone.objects.get(id=sprint_id)
            
            # Verificar permisos
            membership = Membership.objects.get(
                project=sprint.project,
                user=request.user
            )
        except Milestone.DoesNotExist:
            return Response(
                {"error": "Sprint no encontrado"},
                status=status.HTTP_404_NOT_FOUND
            )
        except Membership.DoesNotExist:
            return Response(
                {"error": "No tienes permisos para exportar este review"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Crear workbook
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = f"Sprint Review - {sprint.name}"
        
        # Estilos
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
        
        # Información del Sprint
        ws['A1'] = "Sprint Review"
        ws['A1'].font = Font(bold=True, size=16)
        
        ws['A3'] = "Sprint:"
        ws['B3'] = sprint.name
        ws['A4'] = "Proyecto:"
        ws['B4'] = sprint.project.name
        ws['A5'] = "Fecha inicio:"
        ws['B5'] = sprint.estimated_start.strftime("%d/%m/%Y")
        ws['A6'] = "Fecha fin:"
        ws['B6'] = sprint.estimated_finish.strftime("%d/%m/%Y")
        
        # Métricas generales
        row = 8
        ws[f'A{row}'] = "MÉTRICAS DEL SPRINT"
        ws[f'A{row}'].font = Font(bold=True, size=14)
        
        row += 2
        metrics_headers = ["Métrica", "Valor"]
        for col, header in enumerate(metrics_headers, 1):
            cell = ws.cell(row=row, column=col)
            cell.value = header
            cell.font = header_font
            cell.fill = header_fill
        
        # Calcular métricas
        total_points = sprint.user_stories.aggregate(total=Sum('points'))['total'] or 0
        completed_points = sprint.user_stories.filter(is_closed=True).aggregate(total=Sum('points'))['total'] or 0
        completion_rate = (completed_points/total_points*100) if total_points > 0 else 0
        
        all_feedbacks = SprintReviewEntry.objects.filter(sprint=sprint)
        avg_satisfaction = all_feedbacks.aggregate(avg=Avg('satisfaction_level'))['avg'] or 0
        
        metrics_data = [
            ("Puntos totales planificados", total_points),
            ("Puntos completados", completed_points),
            ("Porcentaje de completitud", f"{completion_rate:.2f}%"),
            ("Satisfacción promedio", f"{avg_satisfaction:.2f}/5"),
            ("Total de reviews recibidos", all_feedbacks.count()),
            ("Sprint aprobado", "Sí" if all_feedbacks.filter(sprint_approved=True).exists() else "No")
        ]
        
        row += 1
        for metric, value in metrics_data:
            ws.cell(row=row, column=1).value = metric
            ws.cell(row=row, column=2).value = value
            row += 1
        
        # Feedback por historia
        row += 2
        ws[f'A{row}'] = "FEEDBACK POR HISTORIA"
        ws[f'A{row}'].font = Font(bold=True, size=14)
        
        row += 2
        story_headers = ["Historia", "Puntos", "Estado", "Calificación promedio", "Aprobaciones"]
        for col, header in enumerate(story_headers, 1):
            cell = ws.cell(row=row, column=col)
            cell.value = header
            cell.font = header_font
            cell.fill = header_fill
        
        row += 1
        completed_stories = sprint.user_stories.filter(is_closed=True)
        
        for story in completed_stories:
            # Calcular métricas por historia
            story_ratings = []
            story_approvals = 0
            
            for feedback in all_feedbacks:
                story_feedback = feedback.completed_stories_feedback.get(str(story.id), {})
                if story_feedback.get('rating'):
                    story_ratings.append(story_feedback['rating'])
                if story_feedback.get('approved'):
                    story_approvals += 1
            
            avg_rating = sum(story_ratings) / len(story_ratings) if story_ratings else 0
            
            ws.cell(row=row, column=1).value = story.subject
            story_points = story.role_points.aggregate(total=Sum('points'))['total'] or 0
            ws.cell(row=row, column=2).value = story_points
            ws.cell(row=row, column=3).value = "Completada"
            ws.cell(row=row, column=4).value = f"{avg_rating:.2f}" if avg_rating > 0 else "Sin calificar"
            ws.cell(row=row, column=5).value = f"{story_approvals}/{all_feedbacks.count()}"
            row += 1
        
        # Feedback individual
        row += 2
        ws[f'A{row}'] = "FEEDBACK DETALLADO"
        ws[f'A{row}'].font = Font(bold=True, size=14)
        
        row += 2
        feedback_headers = ["Usuario", "Satisfacción", "Calidad código", "Funcionalidad", "Aprobado", "Comentarios"]
        for col, header in enumerate(feedback_headers, 1):
            cell = ws.cell(row=row, column=col)
            cell.value = header
            cell.font = header_font
            cell.fill = header_fill
        
        row += 1
        for feedback in all_feedbacks:
            ws.cell(row=row, column=1).value = feedback.user.get_full_name() or feedback.user.username
            ws.cell(row=row, column=2).value = feedback.get_satisfaction_level_display()
            ws.cell(row=row, column=3).value = feedback.code_quality_rating or "N/A"
            ws.cell(row=row, column=4).value = feedback.functionality_rating or "N/A"
            ws.cell(row=row, column=5).value = "Sí" if feedback.sprint_approved else "No"
            ws.cell(row=row, column=6).value = feedback.general_feedback[:100] + "..." if len(feedback.general_feedback) > 100 else feedback.general_feedback
            row += 1
        
        # Ajustar anchos de columna
        for column in ws.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 50)
            ws.column_dimensions[column_letter].width = adjusted_width
        
        # Preparar respuesta
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        filename = f"sprint_review_{sprint.project.slug}_{sprint.name.replace(' ', '_')}.xlsx"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        wb.save(response)
        return response


class SprintRetrospectiveExportView(APIView):
    """Exportar Retrospectiva a Excel"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        sprint_id = request.query_params.get('sprint_id')
        
        if not sprint_id:
            return Response(
                {"error": "sprint_id es requerido"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            sprint = Milestone.objects.get(id=sprint_id)
            retrospective = sprint.retrospective
            
            # Verificar permisos
            membership = Membership.objects.get(
                project=sprint.project,
                user=request.user
            )
        except Milestone.DoesNotExist:
            return Response(
                {"error": "Sprint no encontrado"},
                status=status.HTTP_404_NOT_FOUND
            )
        except SprintRetrospective.DoesNotExist:
            return Response(
                {"error": "No existe retrospectiva para este sprint"},
                status=status.HTTP_404_NOT_FOUND
            )
        except Membership.DoesNotExist:
            return Response(
                {"error": "No tienes permisos para exportar esta retrospectiva"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Crear workbook
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = f"Retrospectiva - {sprint.name}"
        
        # Estilos
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
        good_fill = PatternFill(start_color="92D050", end_color="92D050", fill_type="solid")
        improve_fill = PatternFill(start_color="FFC000", end_color="FFC000", fill_type="solid")
        action_fill = PatternFill(start_color="5B9BD5", end_color="5B9BD5", fill_type="solid")
        
        # Información general
        ws['A1'] = "Sprint Retrospectiva"
        ws['A1'].font = Font(bold=True, size=16)
        
        ws['A3'] = "Sprint:"
        ws['B3'] = sprint.name
        ws['A4'] = "Proyecto:"
        ws['B4'] = sprint.project.name
        ws['A5'] = "Fecha:"
        ws['B5'] = retrospective.created_at.strftime("%d/%m/%Y %H:%M")
        ws['A6'] = "Facilitador:"
        ws['B6'] = retrospective.created_by.get_full_name() if retrospective.created_by else "N/A"
        ws['A7'] = "Estado del equipo:"
        ws['B7'] = retrospective.get_team_mood_display()
        ws['A8'] = "Velocidad alcanzada:"
        ws['B8'] = retrospective.velocity_achieved
        ws['A9'] = "Precisión del compromiso:"
        ws['B9'] = f"{retrospective.commitment_accuracy:.2f}%" if retrospective.commitment_accuracy else "N/A"
        
        # Lo que salió bien
        row = 11
        ws[f'A{row}'] = "LO QUE SALIÓ BIEN"
        ws[f'A{row}'].font = Font(bold=True, size=14)
        ws[f'A{row}'].fill = good_fill
        
        row += 2
        if retrospective.went_well:
            for idx, item in enumerate(retrospective.went_well):
                # Obtener votos del caché
                cache_key = f"retro_vote_{sprint_id}_went_well_{idx}"
                votes = cache.get(cache_key, 0)
                
                ws.cell(row=row, column=1).value = f"• {item['text']}"
                ws.cell(row=row, column=2).value = f"Votos: {votes}"
                row += 1
        else:
            ws.cell(row=row, column=1).value = "No se registraron items"
            row += 1
        
        # A mejorar
        row += 2
        ws[f'A{row}'] = "A MEJORAR"
        ws[f'A{row}'].font = Font(bold=True, size=14)
        ws[f'A{row}'].fill = improve_fill
        
        row += 2
        if retrospective.to_improve:
            for idx, item in enumerate(retrospective.to_improve):
                # Obtener votos del caché
                cache_key = f"retro_vote_{sprint_id}_to_improve_{idx}"
                votes = cache.get(cache_key, 0)
                
                ws.cell(row=row, column=1).value = f"• {item['text']}"
                ws.cell(row=row, column=2).value = f"Votos: {votes}"
                row += 1
        else:
            ws.cell(row=row, column=1).value = "No se registraron items"
            row += 1
        
        # Plan de acción
        row += 2
        ws[f'A{row}'] = "PLAN DE ACCIÓN"
        ws[f'A{row}'].font = Font(bold=True, size=14)
        ws[f'A{row}'].fill = action_fill
        
        row += 2
        action_headers = ["Acción", "Responsable", "Fecha límite", "Estado"]
        for col, header in enumerate(action_headers, 1):
            cell = ws.cell(row=row, column=col)
            cell.value = header
            cell.font = header_font
            cell.fill = header_fill
        
        row += 1
        if retrospective.action_items:
            for action in retrospective.action_items:
                # Obtener nombre del responsable
                responsible_name = "No asignado"
                if action.get('responsible_id'):
                    try:
                        user = User.objects.get(id=action['responsible_id'])
                        responsible_name = user.get_full_name() or user.username
                    except User.DoesNotExist:
                        pass
                
                ws.cell(row=row, column=1).value = action.get('action', '')
                ws.cell(row=row, column=2).value = responsible_name
                ws.cell(row=row, column=3).value = action.get('due_date', 'Sin fecha')
                ws.cell(row=row, column=4).value = "Completada" if action.get('completed') else "Pendiente"
                row += 1
        else:
            ws.cell(row=row, column=1).value = "No se definieron acciones"
        
        # Acciones previas completadas
        if retrospective.previous_actions_completed:
            row += 2
            ws[f'A{row}'] = "ACCIONES PREVIAS COMPLETADAS"
            ws[f'A{row}'].font = Font(bold=True, size=14)
            
            row += 2
            for action in retrospective.previous_actions_completed:
                ws.cell(row=row, column=1).value = f"✓ {action.get('action', 'Acción sin descripción')}"
                row += 1
        
        # Ajustar anchos de columna
        for column in ws.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 60)
            ws.column_dimensions[column_letter].width = adjusted_width
        
        # Preparar respuesta
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        filename = f"retrospectiva_{sprint.project.slug}_{sprint.name.replace(' ', '_')}.xlsx"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        wb.save(response)
        return response

