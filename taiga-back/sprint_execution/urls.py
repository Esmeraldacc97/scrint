# sprint_execution/urls.py - VERSIÓN LIMPIA

from django.urls import path, include
from .views import (
    # Task Selection
    TaskSelectionView, TaskSelectionCreateView, UnselectTaskView, 
    ResumenTareasSeleccionadasView, BulkSelectTasksView,
    
    # Task Management
    UpdateTaskStatusView, TaskStatusSummaryView,
    
    # Sprint Metrics
    BurndownChartView, TeamVelocityView, SprintRemainingDaysView, 
    SprintSummaryView, SprintSummaryExportView,
    
    # Sprint Ceremonies
    SprintReviewEntryView, SprintClosureView, SprintRetrospectiveView, 
    SprintExportView, SprintReviewExportView,
    SprintRetrospectiveExportView, RetrospectiveVoteView,
    
    # Daily Meeting
    DailyMeetingListView, DailyMeetingDetailView, DailyMeetingTodayView,
    DailyResponseCreateView, DailyResponseDetailView, DailyMeetingExportView
)
from .sse import task_event_stream

urlpatterns = [

    # Task Selection
    path('task-selection/', TaskSelectionView.as_view(), name='task_selection'),
    path('task-selection/select/', TaskSelectionCreateView.as_view(), name='task_selection_create'),
    path('task-selection/unselect/', UnselectTaskView.as_view(), name='task_unselect'),
    path('task-selection/summary/', ResumenTareasSeleccionadasView.as_view(), name='task_summary'),
    path('bulk-select-tasks/', BulkSelectTasksView.as_view(), name='bulk_select_tasks'),
    path("task-selection/events/", task_event_stream, name="task_events"),
    
    # Task Management
    path("task-update-status/", UpdateTaskStatusView.as_view(), name="task_update_status"),
    path("task-status-summary/", TaskStatusSummaryView.as_view(), name="task_status_summary"),
    
    # Sprint Metrics
    path('burndown-chart/', BurndownChartView.as_view(), name='burndown_chart'),
    path('team-velocity/', TeamVelocityView.as_view(), name='team_velocity'),
    path("sprint-remaining-days/", SprintRemainingDaysView.as_view(), name="sprint_remaining_days"),
    path('sprint-summary/', SprintSummaryView.as_view(), name='sprint_summary'),
    path('sprint-summary/export/', SprintSummaryExportView.as_view(), name='sprint_summary_export'),
    
    # Sprint Ceremonies
    # Sprint Review - actualizar estas rutas
    path('sprint-review/', SprintReviewEntryView.as_view(), name='sprint_review_entry'),
    path('sprint-review/export/', SprintReviewExportView.as_view(), name='sprint_review_export'),
    path("sprint-closure/", SprintClosureView.as_view(), name="sprint-closure"),

    # Sprint Retrospective - actualizar estas rutas
    path('sprint-retrospective/', SprintRetrospectiveView.as_view(), name='sprint_retrospective'),
    path('sprint-retrospective/export/', SprintRetrospectiveExportView.as_view(), name='sprint_retrospective_export'),
    path('retrospective-vote/', RetrospectiveVoteView.as_view(), name='retrospective_vote'),
    
    path("sprint-export/", SprintExportView.as_view(), name="sprint-export"),

    
    
    # Daily Meeting
    path('daily-meetings/', DailyMeetingListView.as_view(), name='daily_meeting_list'),
    path('daily-meetings/today/', DailyMeetingTodayView.as_view(), name='daily_meeting_today'),
    path('daily-meetings/<int:meeting_id>/', DailyMeetingDetailView.as_view(), name='daily_meeting_detail'),
    path('daily-meetings/<int:meeting_id>/response/', DailyResponseCreateView.as_view(), name='daily_response_create'),
    path('daily-meetings/<int:meeting_id>/my-response/', DailyResponseDetailView.as_view(), name='daily_response_detail'),
    path('daily-meetings/<int:meeting_id>/export/', DailyMeetingExportView.as_view(), name='daily_meeting_export'),
]