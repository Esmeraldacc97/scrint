from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PlanningSessionViewSet, ParticipantViewSet, EstimationViewSet, PlanningSessionStatusViewSet, sse_notifications, TeamCapacityView, ValidateTeamCapacityView, BacklogUserStoriesView


router = DefaultRouter()
router.register(r'planning-sessions', PlanningSessionViewSet, basename='planning-session')
router.register(r'participants', ParticipantViewSet, basename='participant')
router.register(r'estimations', EstimationViewSet, basename='estimation')
router.register(r'planning-sessions-status', PlanningSessionStatusViewSet, basename='planning-session-status')
router.register(r'planning-sessions/status', PlanningSessionStatusViewSet, basename="planning-session-status")


urlpatterns = [
    path('', include(router.urls)),
    path('notifications/stream/', sse_notifications, name='sse_notifications'),
    path('team-capacity/', TeamCapacityView.as_view(), name='team_capacity'),
    path('team-capacity/validate/', ValidateTeamCapacityView.as_view(), name='validate_team_capacity'),
    path('backlog-userstories/<int:project_id>/', BacklogUserStoriesView.as_view(), name='backlog_userstories')
]
