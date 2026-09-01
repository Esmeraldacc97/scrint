# sprint_execution/permissions.py

from rest_framework import permissions
from taiga.projects.models import Membership


class IsScrumMaster(permissions.BasePermission):
    """
    Permiso personalizado para verificar si el usuario es Scrum Master
    """
    message = "Solo el Scrum Master puede realizar esta acción."
    
    def has_permission(self, request, view):
        # Para métodos de lectura, permitir a todos los miembros
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Para otros métodos, verificar rol de Scrum Master
        project_id = request.data.get('project_id') or request.query_params.get('project_id')
        sprint_id = request.data.get('sprint_id') or request.query_params.get('sprint_id')
        
        if sprint_id:
            try:
                from taiga.projects.milestones.models import Milestone
                sprint = Milestone.objects.get(id=sprint_id)
                project_id = sprint.project.id
            except Milestone.DoesNotExist:
                return False
        
        if not project_id:
            return False
        
        try:
            membership = Membership.objects.get(
                project_id=project_id,
                user=request.user
            )
            return membership.role.slug == 'scrum-master'
        except Membership.DoesNotExist:
            return False


class IsProductOwner(permissions.BasePermission):
    """
    Permiso personalizado para verificar si el usuario es Product Owner
    """
    message = "Solo el Product Owner puede realizar esta acción."
    
    def has_permission(self, request, view):
        project_id = request.data.get('project_id') or request.query_params.get('project_id')
        sprint_id = request.data.get('sprint_id') or request.query_params.get('sprint_id')
        
        if sprint_id:
            try:
                from taiga.projects.milestones.models import Milestone
                sprint = Milestone.objects.get(id=sprint_id)
                project_id = sprint.project.id
            except Milestone.DoesNotExist:
                return False
        
        if not project_id:
            return False
        
        try:
            membership = Membership.objects.get(
                project_id=project_id,
                user=request.user
            )
            return membership.role.slug == 'product-owner'
        except Membership.DoesNotExist:
            return False


class IsProjectMember(permissions.BasePermission):
    """
    Permiso personalizado para verificar si el usuario es miembro del proyecto
    """
    message = "Debes ser miembro del proyecto para realizar esta acción."
    
    def has_permission(self, request, view):
        project_id = request.data.get('project_id') or request.query_params.get('project_id')
        sprint_id = request.data.get('sprint_id') or request.query_params.get('sprint_id')
        
        if sprint_id:
            try:
                from taiga.projects.milestones.models import Milestone
                sprint = Milestone.objects.get(id=sprint_id)
                project_id = sprint.project.id
            except Milestone.DoesNotExist:
                return False
        
        if not project_id:
            return False
        
        return Membership.objects.filter(
            project_id=project_id,
            user=request.user
        ).exists()


class IsDevelopmentTeam(permissions.BasePermission):
    """
    Permiso para verificar si el usuario es parte del Development Team
    """
    message = "Solo el Development Team puede realizar esta acción."
    
    def has_permission(self, request, view):
        project_id = request.data.get('project_id') or request.query_params.get('project_id')
        sprint_id = request.data.get('sprint_id') or request.query_params.get('sprint_id')
        
        if sprint_id:
            try:
                from taiga.projects.milestones.models import Milestone
                sprint = Milestone.objects.get(id=sprint_id)
                project_id = sprint.project.id
            except Milestone.DoesNotExist:
                return False
        
        if not project_id:
            return False
        
        try:
            membership = Membership.objects.get(
                project_id=project_id,
                user=request.user
            )
            # Development team = todos excepto PO, SM y Stakeholder
            return membership.role.slug not in ['product-owner', 'scrum-master', 'stakeholder']
        except Membership.DoesNotExist:
            return False


class CanApproveSprintReview(permissions.BasePermission):
    """
    Permiso para aprobar Sprint Review (solo Product Owner)
    """
    message = "Solo el Product Owner puede aprobar el Sprint Review."
    
    def has_permission(self, request, view):
        # Si no está intentando aprobar, permitir
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Si está intentando aprobar, verificar que sea PO
        if request.data.get('sprint_approved', False):
            return IsProductOwner().has_permission(request, view)
        
        return True


class CanManageRetrospective(permissions.BasePermission):
    """
    Permiso para gestionar retrospectivas (solo Scrum Master para crear/editar)
    """
    message = "Solo el Scrum Master puede gestionar retrospectivas."
    
    def has_permission(self, request, view):
        # Para lectura, permitir a todos los miembros
        if request.method in permissions.SAFE_METHODS:
            return IsProjectMember().has_permission(request, view)
        
        # Para escritura, solo Scrum Master
        return IsScrumMaster().has_permission(request, view)