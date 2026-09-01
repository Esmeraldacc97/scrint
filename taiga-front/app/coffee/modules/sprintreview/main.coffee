###
# Sprint Review Controller
###

taiga = @.taiga
mixOf = @.taiga.mixOf

module = angular.module("taigaSprintReview")

#############################################################################
## Sprint Review Controller
#############################################################################

class SprintReviewController extends mixOf(taiga.Controller, taiga.PageMixin)
    @.$inject = [
        "$scope",
        "$rootScope",
        "$tgRepo",
        "$tgResources",
        "$routeParams",
        "$q",
        "$tgLocation",
        "$tgNavUrls",
        "tgAppMetaService",
        "$tgAuth",
        "$translate",
        "tgProjectService",
        "$tgConfirm",
        "$interval"
    ]

    constructor: (@scope, @rootscope, @repo, @rs, @params, @q, @location, @navUrls, @appMetaService, @auth,
                  @translate, @projectService, @confirm, @interval) ->

        @scope.sectionName = "SPRINT_REVIEW.SECTION_NAME"
        
        # Inicializar variables
        @scope.selectedSprintId = null
        @scope.sprintData = null
        @scope.completedStories = []
        @scope.metrics = {}
        @scope.existingFeedback = null
        @scope.allFeedbacks = []
        @scope.submitting = false
        @scope.loading = true
        @scope.error = null
        @scope.activeTab = 'overview'
        
        # Inicializar feedback vacío
        @scope.feedbackForm = {
            general_feedback: ''
            satisfaction_level: 3
            stories_feedback: {}
            sprint_approved: false
            requires_changes: ''
            code_quality_rating: null
            functionality_rating: null
        }
        
        # Opciones de satisfacción
        @scope.satisfactionOptions = [
            {value: 1, text: 'SPRINT_REVIEW.VERY_UNSATISFIED', emoji: '😞'},
            {value: 2, text: 'SPRINT_REVIEW.UNSATISFIED', emoji: '😕'},
            {value: 3, text: 'SPRINT_REVIEW.NEUTRAL', emoji: '😐'},
            {value: 4, text: 'SPRINT_REVIEW.SATISFIED', emoji: '🙂'},
            {value: 5, text: 'SPRINT_REVIEW.VERY_SATISFIED', emoji: '😊'}
        ]
        
        # Opciones de calificación
        @scope.ratingOptions = [1, 2, 3, 4, 5]
        
        # Funciones del scope
        @scope.loadSprintReview = => @.loadSprintReview()
        @scope.submitFeedback = => @.submitFeedback()
        @scope.editFeedback = => @.editFeedback()
        @scope.exportToExcel = => @.exportToExcel()
        @scope.setActiveTab = (tab) => @.setActiveTab(tab)
        @scope.isActiveTab = (tab) => @scope.activeTab == tab
        @scope.toggleStoryApproval = (storyId) => @.toggleStoryApproval(storyId)
        @scope.updateStoryRating = (storyId, rating) => @.updateStoryRating(storyId, rating)
        @scope.updateStoryComment = (storyId, comment) => @.updateStoryComment(storyId, comment)
        @scope.approveSprint = => @.approveSprint()
        @scope.rejectSprint = => @.rejectSprint()
        @scope.getStatusClass = (level) => @.getStatusClass(level)
        @scope.getStarClass = (star, rating) => @.getStarClass(star, rating)
        @scope.setSatisfactionLevel = (level) => @.setSatisfactionLevel(level)
        @scope.isSatisfactionSelected = (level) => @.isSatisfactionSelected(level)
        
        # Cargar datos iniciales
        promise = @.loadInitialData()

        promise.then =>
            title = @translate.instant("SPRINT_REVIEW.PAGE_TITLE", {projectName: @scope.project.name})
            description = @translate.instant("SPRINT_REVIEW.PAGE_DESCRIPTION", {
                projectName: @scope.project.name
            })
            @appMetaService.setAll(title, description)

        promise.then null, @.onInitialDataError.bind(@)

    loadProject: ->
        project = @projectService.project.toJS()
        @scope.projectId = project.id
        @scope.project = project
        
        # Cargar usuarios y roles como en Daily Scrum
        @.fillUsersAndRoles(project.members, project.roles)
        @scope.activeUsers = angular.copy(@scope.users)
        
        # Obtener TODOS los sprints del proyecto (cerrados y abiertos)
        @scope.sprints = project.milestones || []
        
        console.log "Total sprints encontrados:", @scope.sprints.length
        console.log "Sprints:", @scope.sprints
        
        # Si hay un sprint en la URL, seleccionarlo
        if @params.sprint
            @scope.selectedSprintId = parseInt(@params.sprint)
        # Si no, buscar el sprint más reciente (cerrado o no)
        else if @scope.sprints.length > 0
            # Ordenar por fecha de fin y tomar el más reciente
            sortedSprints = _.sortBy @scope.sprints, (s) -> 
                return -new Date(s.estimated_finish).getTime()
            @scope.selectedSprintId = sortedSprints[0].id
            console.log "Sprint seleccionado automáticamente:", @scope.selectedSprintId
        
        @scope.$emit('project:loaded', project)
        return project

    loadMembers: ->
        user = @auth.getUser()
        @scope.user = user
        userId = parseInt(user?.id)
        
        console.log "Usuario actual:", user
        console.log "User ID:", userId
        console.log "Active users después de fillUsersAndRoles:", @scope.activeUsers
        
        # Encontrar el usuario actual en activeUsers
        @scope.currentUser = _.find @scope.activeUsers, (member) ->
            return parseInt(member.id) == userId
        
        # Obtener la lista de miembros sin el usuario actual
        @scope.memberships = _.reject @scope.activeUsers, (member) ->
            return parseInt(member.id) == userId
        
        console.log "Current user encontrado:", @scope.currentUser
        console.log "Memberships:", @scope.memberships
        
        # Determinar rol desde currentUser
        if @scope.currentUser
            roleName = @scope.currentUser.role_name
            
            console.log "Rol encontrado:", roleName
            
            @scope.userRole = roleName
            
            # Asignar flags de rol
            if roleName
                roleNameLower = roleName.toLowerCase()
                @scope.isScrumMaster = roleNameLower.includes('scrum master') or roleNameLower == 'scrum-master'
                @scope.isDevelopmentTeam = not (roleNameLower.includes('product owner') or 
                                            roleNameLower.includes('scrum master') or 
                                            roleNameLower.includes('stakeholder'))
                @scope.isProductOwner = roleNameLower.includes('product owner') or roleNameLower == 'product-owner'
                @scope.isStakeholder = roleNameLower.includes('stakeholder')
                
            console.log "Roles asignados:"
            console.log "  - isScrumMaster:", @scope.isScrumMaster
            console.log "  - isDevelopmentTeam:", @scope.isDevelopmentTeam
            console.log "  - isProductOwner:", @scope.isProductOwner
            console.log "  - isStakeholder:", @scope.isStakeholder

    loadInitialData: ->
        project = @.loadProject()
        @.loadMembers()
        
        # Debug - verificar que tenemos projectId
        console.log "Project ID en loadInitialData:", @scope.projectId
        
        # Cargar el sprint review si hay un sprint seleccionado
        if @scope.selectedSprintId
            return @.loadSprintReview()
        else
            @scope.loading = false
            return @q.when()

    loadSprintReview: ->
        return unless @scope.selectedSprintId
        
        @scope.loading = true
        @scope.error = null
        
        console.log "Cargando Sprint Review para sprint ID:", @scope.selectedSprintId
        
        promise = @rs.sprintReview.get(@scope.selectedSprintId)
        
        promise.then (response) =>
            console.log "Sprint Review response:", response
            @scope.loading = false
            
            # Procesar datos del sprint
            @scope.sprintData = response.sprint
            
            # Eliminar historias duplicadas usando el ID
            storiesMap = {}
            if response.completed_stories and response.completed_stories.length > 0
                for story in response.completed_stories
                    if story.id and not storiesMap[story.id]
                        storiesMap[story.id] = story
                
                @scope.completedStories = _.values(storiesMap)
            else
                @scope.completedStories = []
            
            console.log "Historias únicas cargadas:", @scope.completedStories.length
            
            @scope.metrics = response.metrics || {}
            @scope.existingFeedback = response.existing_feedback
            @scope.canApprove = response.can_approve
            
            # Si el backend envía todos los feedbacks, usarlos
            if response.all_feedbacks and response.all_feedbacks.length > 0
                @scope.allFeedbacks = response.all_feedbacks
                console.log "Feedbacks del equipo recibidos:", @scope.allFeedbacks.length
            else
                @scope.allFeedbacks = []
            
            # Si hay feedback existente, cargar en el formulario
            if @scope.existingFeedback
                @.loadExistingFeedback()
            else
                # Inicializar feedback para cada historia
                @.initializeStoriesFeedback()
            
            # Solo cargar feedbacks adicionales si es PO o SM y no vinieron en la respuesta
            if (@scope.isProductOwner or @scope.isScrumMaster) and @scope.allFeedbacks.length == 0
                @.loadAllFeedbacks()
            
        .catch (error) =>
            console.error "Error cargando Sprint Review:", error
            @scope.loading = false
            @scope.error = error.data?.error or @translate.instant("COMMON.ERROR")

    initializeStoriesFeedback: ->
        # Inicializar feedback vacío para cada historia
        for story in @scope.completedStories
            @scope.feedbackForm.stories_feedback[story.id] = {
                approved: false
                rating: null
                comments: ''
            }

    loadExistingFeedback: ->
        # Cargar feedback existente en el formulario
        feedback = @scope.existingFeedback
        
        @scope.feedbackForm = {
            general_feedback: feedback.general_feedback
            satisfaction_level: feedback.satisfaction_level
            stories_feedback: feedback.completed_stories_feedback or {}
            sprint_approved: feedback.sprint_approved
            requires_changes: feedback.requires_changes
            code_quality_rating: feedback.code_quality_rating
            functionality_rating: feedback.functionality_rating
        }
        
        # Asegurar que todas las historias tengan feedback
        for story in @scope.completedStories
            if not @scope.feedbackForm.stories_feedback[story.id]
                @scope.feedbackForm.stories_feedback[story.id] = {
                    approved: false
                    rating: null
                    comments: ''
                }

    loadAllFeedbacks: ->
        # Cargar todos los feedbacks del sprint
        console.log "Cargando feedbacks del equipo para sprint:", @scope.selectedSprintId
        
        # Inicializar array vacío
        @scope.allFeedbacks = []
        
        # Intentar cargar feedbacks del backend
        promise = @rs.sprintReview.list(@scope.selectedSprintId)
        
        promise.then (feedbacks) =>
            console.log "Feedbacks recibidos del backend:", feedbacks
            
            if feedbacks and feedbacks.length > 0
                # Usar los feedbacks del backend
                @scope.allFeedbacks = feedbacks
            else
                # Si no hay feedbacks del backend, al menos mostrar el actual si existe
                if @scope.existingFeedback and @scope.currentUser
                    feedbackData = {
                        id: @scope.existingFeedback.id
                        user: @scope.currentUser
                        user_name: @scope.existingFeedback.user_name or (@scope.currentUser.full_name_display or @scope.currentUser.full_name or @scope.currentUser.username)
                        user_role: @scope.existingFeedback.user_role or @scope.currentUser.role_name
                        satisfaction_level: @scope.existingFeedback.satisfaction_level
                        satisfaction_display: @scope.existingFeedback.satisfaction_display
                        general_feedback: @scope.existingFeedback.general_feedback
                        code_quality_rating: @scope.existingFeedback.code_quality_rating
                        functionality_rating: @scope.existingFeedback.functionality_rating
                        average_story_rating: @scope.existingFeedback.average_story_rating
                        sprint_approved: @scope.existingFeedback.sprint_approved
                        requires_changes: @scope.existingFeedback.requires_changes
                        created_at: @scope.existingFeedback.created_at
                        updated_at: @scope.existingFeedback.updated_at
                    }
                    @scope.allFeedbacks.push(feedbackData)
            
            console.log "Total feedbacks cargados:", @scope.allFeedbacks.length
            
        .catch (error) =>
            console.error "Error cargando feedbacks:", error
            
            # En caso de error, mostrar al menos el feedback actual
            if @scope.existingFeedback and @scope.currentUser
                feedbackData = {
                    id: @scope.existingFeedback.id
                    user: @scope.currentUser
                    user_name: @scope.existingFeedback.user_name or (@scope.currentUser.full_name_display or @scope.currentUser.full_name or @scope.currentUser.username)
                    user_role: @scope.existingFeedback.user_role or @scope.currentUser.role_name
                    satisfaction_level: @scope.existingFeedback.satisfaction_level
                    satisfaction_display: @scope.existingFeedback.satisfaction_display
                    general_feedback: @scope.existingFeedback.general_feedback
                    code_quality_rating: @scope.existingFeedback.code_quality_rating
                    functionality_rating: @scope.existingFeedback.functionality_rating
                    average_story_rating: @scope.existingFeedback.average_story_rating
                    sprint_approved: @scope.existingFeedback.sprint_approved
                    requires_changes: @scope.existingFeedback.requires_changes
                    created_at: @scope.existingFeedback.created_at
                    updated_at: @scope.existingFeedback.updated_at
                }
                @scope.allFeedbacks.push(feedbackData)

    submitFeedback: ->
        return unless @scope.selectedSprintId
        
        @scope.submitting = true
        
        # Preparar datos para enviar
        data = {
            sprint_id: @scope.selectedSprintId
            general_feedback: @scope.feedbackForm.general_feedback
            satisfaction_level: @scope.feedbackForm.satisfaction_level
            stories_feedback: @scope.feedbackForm.stories_feedback
            code_quality_rating: @scope.feedbackForm.code_quality_rating
            functionality_rating: @scope.feedbackForm.functionality_rating
        }
        
        # Solo el PO puede aprobar/rechazar
        if @scope.isProductOwner
            data.sprint_approved = @scope.feedbackForm.sprint_approved
            data.requires_changes = @scope.feedbackForm.requires_changes
        
        console.log "Enviando feedback:", data
        
        promise = @rs.sprintReview.create(data)
        
        promise.then (response) =>
            console.log "Feedback enviado exitosamente:", response
            @scope.submitting = false
            @confirm.notify('success', null, @translate.instant('SPRINT_REVIEW.FEEDBACK_SUBMITTED'))
            
            # Recargar datos
            @.loadSprintReview()
            
        .catch (error) =>
            console.error "Error al enviar feedback:", error
            @scope.submitting = false
            errorMsg = error.data?.error or @translate.instant("COMMON.ERROR")
            @confirm.notify('error', null, errorMsg)

    editFeedback: ->
        # Permitir editar el feedback
        @scope.existingFeedback = null

    setActiveTab: (tab) ->
        @scope.activeTab = tab

    toggleStoryApproval: (storyId) ->
        if @scope.feedbackForm.stories_feedback[storyId]
            @scope.feedbackForm.stories_feedback[storyId].approved = 
                !@scope.feedbackForm.stories_feedback[storyId].approved

    updateStoryRating: (storyId, rating) ->
        if @scope.feedbackForm.stories_feedback[storyId]
            @scope.feedbackForm.stories_feedback[storyId].rating = rating

    updateStoryComment: (storyId, comment) ->
        if @scope.feedbackForm.stories_feedback[storyId]
            @scope.feedbackForm.stories_feedback[storyId].comments = comment

    approveSprint: ->
        return unless @scope.isProductOwner
        
        @scope.feedbackForm.sprint_approved = true
        @scope.feedbackForm.requires_changes = ''
        @.submitFeedback()

    rejectSprint: ->
        return unless @scope.isProductOwner
        
        # Mostrar modal para cambios requeridos
        @confirm.ask(
            @translate.instant("SPRINT_REVIEW.REJECT_TITLE"),
            null,
            @translate.instant("SPRINT_REVIEW.REJECT_SUBTITLE"),
            @translate.instant("SPRINT_REVIEW.CHANGES_REQUIRED_PLACEHOLDER")
        ).then (result) =>
            if result.finish
                @scope.feedbackForm.sprint_approved = false
                @scope.feedbackForm.requires_changes = result.response
                @.submitFeedback()

    exportToExcel: ->
        return unless @scope.selectedSprintId
        
        console.log "Export clicked - Sprint ID:", @scope.selectedSprintId
        
        # Notificar inicio
        try
            @confirm.notify('info', null, @translate.instant('SPRINT_REVIEW.GENERATING_EXCEL'))
        catch e
            console.log "Notificación no disponible"
        
        # Construir URL
        baseUrl = "/api/v1/sprint-review/export/"
        
        console.log "Export URL base:", baseUrl
        
        # Obtener el token de autenticación
        token = @auth.getToken()
        
        # Usar fetch para descargar el archivo con autenticación
        # Incluir sprint_id como parámetro de query
        fetchUrl = "#{baseUrl}?sprint_id=#{@scope.selectedSprintId}"
        console.log "Fetch URL completa:", fetchUrl
        
        fetch(fetchUrl, {
            method: 'GET',
            headers: {
                'Authorization': "Bearer #{token}"
                'X-Session-Token': token
            },
            credentials: 'include'
        })
        .then (response) =>
            console.log "Response status:", response.status
            if not response.ok
                throw new Error("Error al descargar: #{response.status}")
            return response.blob()
        .then (blob) =>
            console.log "Blob recibido, tamaño:", blob.size
            
            # Crear URL del blob
            url = window.URL.createObjectURL(blob)
            
            # Crear enlace de descarga
            link = document.createElement('a')
            link.href = url
            sprintName = @scope.sprintData?.name or @scope.selectedSprintId
            link.download = "sprint_review_#{sprintName}.xlsx"
            
            # Simular clic
            document.body.appendChild(link)
            link.click()
            
            # Limpiar
            setTimeout ->
                document.body.removeChild(link)
                window.URL.revokeObjectURL(url)
            , 100
            
            console.log "Descarga completada"
            
            # Notificar éxito
            try
                @confirm.notify('success', null, @translate.instant('SPRINT_REVIEW.DOWNLOAD_COMPLETE'))
            catch e
                console.log "Notificación no disponible"
                
        .catch (error) =>
            console.error "Error al exportar:", error
            try
                @confirm.notify('error', null, @translate.instant('SPRINT_REVIEW.EXPORT_ERROR'))
            catch e
                console.log "Notificación no disponible"

    getStatusClass: (level) ->
        if level <= 2
            return 'status-bad'
        else if level == 3
            return 'status-neutral'
        else
            return 'status-good'

    getStarClass: (star, rating) ->
        if star <= rating
            return 'star-filled'
        else
            return 'star-empty'

    setSatisfactionLevel: (level) ->
        @scope.feedbackForm.satisfaction_level = level
        console.log "Satisfaction level set to:", level

    isSatisfactionSelected: (level) ->
        return @scope.feedbackForm.satisfaction_level == level

module.controller("SprintReviewController", SprintReviewController)


#############################################################################
## Sprint Review Menu Directive
#############################################################################

SprintReviewMenuDirective = ($translate) ->
    return {
        template: """
        <div class="sprint-review-menu">
            <h3>{{ 'SPRINT_REVIEW.MENU_TITLE' | translate }}</h3>
            
            <div class="menu-section" ng-if="selectedSprintId && metrics">
                <h4>{{ 'SPRINT_REVIEW.SPRINT_METRICS' | translate }}</h4>
                <div class="stats-list">
                    <div class="stat">
                        <span class="label">{{ 'SPRINT_REVIEW.COMPLETION_RATE' | translate }}:</span>
                        <span class="value">{{ metrics.completion_rate }}%</span>
                    </div>
                    <div class="stat">
                        <span class="label">{{ 'SPRINT_REVIEW.TOTAL_POINTS' | translate }}:</span>
                        <span class="value">{{ metrics.total_points }}</span>
                    </div>
                    <div class="stat">
                        <span class="label">{{ 'SPRINT_REVIEW.COMPLETED_POINTS' | translate }}:</span>
                        <span class="value">{{ metrics.completed_points }}</span>
                    </div>
                    <div class="stat" ng-if="metrics.avg_satisfaction > 0">
                        <span class="label">{{ 'SPRINT_REVIEW.AVG_SATISFACTION' | translate }}:</span>
                        <span class="value">{{ metrics.avg_satisfaction }}/5</span>
                    </div>
                </div>
            </div>
            
            <div class="menu-section" ng-if="existingFeedback">
                <h4>{{ 'SPRINT_REVIEW.YOUR_FEEDBACK' | translate }}</h4>
                <p class="status-complete">
                    <tg-svg svg-icon="icon-check-circle"></tg-svg>
                    {{ 'SPRINT_REVIEW.FEEDBACK_SUBMITTED_STATUS' | translate }}
                </p>
            </div>
        </div>
        """
        scope: false
    }

module.directive("tgSprintReviewMenu", ["$translate", SprintReviewMenuDirective])