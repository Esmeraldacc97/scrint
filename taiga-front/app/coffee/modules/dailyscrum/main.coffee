###
# Daily Scrum Controller
###

taiga = @.taiga
mixOf = @.taiga.mixOf

module = angular.module("taigaDailyScrum")

#############################################################################
## Daily Scrum Controller
#############################################################################

class DailyScrumController extends mixOf(taiga.Controller, taiga.PageMixin)
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

        @scope.sectionName = "DAILY.SECTION_NAME"
        
        # Inicializar variables
        @scope.selectedDate = new Date()
        @scope.maxDate = new Date().toISOString().split('T')[0]
        @scope.dailyMeeting = null
        @scope.myResponse = null
        @scope.hasResponded = false
        @scope.submitting = false
        @scope.loading = true
        @scope.error = null
        @scope.blockersCount = 0
        
        # Opciones de estado de ánimo
        @scope.moodOptions = [
            {value: 'great', emoji: '😊', text: 'DAILY.MOOD_GREAT'},
            {value: 'good', emoji: '🙂', text: 'DAILY.MOOD_GOOD'},
            {value: 'neutral', emoji: '😐', text: 'DAILY.MOOD_NEUTRAL'},
            {value: 'bad', emoji: '😕', text: 'DAILY.MOOD_BAD'},
            {value: 'terrible', emoji: '😞', text: 'DAILY.MOOD_TERRIBLE'}
        ]
        
        # Inicializar respuesta vacía
        @scope.dailyResponse = {
            yesterday_work: ''
            today_plan: ''
            blockers: ''
            mood: 'neutral'
        }
        
        # Funciones del scope
        @scope.loadDailyMeeting = => @.loadDailyMeeting()
        @scope.submitDailyResponse = => @.submitDailyResponse()
        @scope.editResponse = => @.editResponse()
        @scope.exportToExcel = => @.exportToExcel()
        @scope.getMoodEmoji = (mood) => @.getMoodEmoji(mood)
        @scope.getMoodText = (mood) => @.getMoodText(mood)
        @scope.getMoodPercentage = (mood) => @.getMoodPercentage(mood)
        @scope.getTotalResponses = => @.getTotalResponses()
        @scope.previousDay = => @.previousDay()
        @scope.nextDay = => @.nextDay()
        @scope.isToday = => @.isToday()
        @scope.createTodayMeeting = => @.createTodayMeeting()
        @scope.refreshData = => @.refreshData()
        
        # Auto-refresh para SM
        @autoRefreshInterval = null
        
        # Cargar datos iniciales
        promise = @.loadInitialData()

        promise.then =>
            title = @translate.instant("DAILY.PAGE_TITLE", {projectName: @scope.project.name})
            description = @translate.instant("DAILY.PAGE_DESCRIPTION", {
                projectName: @scope.project.name
            })
            @appMetaService.setAll(title, description)

        promise.then null, @.onInitialDataError.bind(@)
        
        # Limpiar intervalos al destruir
        @scope.$on '$destroy', =>
            if @autoRefreshInterval
                @interval.cancel(@autoRefreshInterval)

    loadProject: ->
        project = @projectService.project.toJS()
        @scope.projectId = project.id
        @scope.project = project
        
        # Cargar usuarios y roles como en Planning Poker
        @.fillUsersAndRoles(project.members, project.roles)
        @scope.activeUsers = angular.copy(@scope.users)
        
        @scope.$emit('project:loaded', project)
        return project

    loadMembers: ->
        user = @auth.getUser()
        @scope.user = user
        userId = parseInt(user?.id)
        
        console.log "Usuario actual:", user
        console.log "User ID:", userId
        console.log "Active users después de fillUsersAndRoles:", @scope.activeUsers
        
        # Encontrar el usuario actual en activeUsers (usando el mismo patrón que Planning Poker)
        @scope.currentUser = _.find @scope.activeUsers, (member) ->
            return parseInt(member.id) == userId
        
        # Obtener la lista de miembros sin el usuario actual
        @scope.memberships = _.reject @scope.activeUsers, (member) ->
            return parseInt(member.id) == userId
        
        console.log "Current user encontrado:", @scope.currentUser
        console.log "Memberships:", @scope.memberships
        
        # Determinar rol desde currentUser
        if @scope.currentUser
            # En Planning Poker usan role_name directamente
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
        
        # Cargar el daily meeting actual
        return @.loadDailyMeeting()

    loadDailyMeeting: ->
        console.log "loadDailyMeeting - @scope.projectId:", @scope.projectId
        console.log "loadDailyMeeting - tipo:", typeof @scope.projectId
        
        return unless @scope.projectId
        
        @scope.loading = true
        @scope.error = null
        
        dateStr = @scope.selectedDate.toISOString().split('T')[0]
        isToday = dateStr == new Date().toISOString().split('T')[0]
        
        if isToday
            # Asegúrate de que se pasa como número
            projectId = parseInt(@scope.projectId)
            console.log "Llamando getDailyMeetingToday con:", projectId
            promise = @rs.dailyMeetings.getDailyMeetingToday(projectId)
        else
            params = {
                project: @scope.projectId
                date: dateStr
            }
            promise = @rs.dailyMeetings.list(params).then (meetings) ->
                if meetings and meetings.length > 0
                    return meetings[0]
                return null
        
        promise.then (response) =>
            @scope.loading = false
            @scope.dailyMeeting = response
            
            if @scope.dailyMeeting
                @.processDailyMeeting()
                @.checkMyResponse()
            else
                @scope.hasResponded = false
                @scope.myResponse = null
            
        .catch (error) =>
            @scope.loading = false
            
            # Manejar el caso específico del 404 para "No hay Daily Meeting"
            if error.status == 404 and error.data?.error
                @scope.dailyMeeting = null
                @scope.error = error.data.error
                
                # Si es Scrum Master, mostrar opción de crear
                if @scope.isScrumMaster and isToday
                    @scope.showCreateOption = true
            else
                @scope.error = error.data?.error or @translate.instant("COMMON.ERROR")

    processDailyMeeting: ->
        return unless @scope.dailyMeeting
        
        # Debug - verificar estructura de datos
        console.log "Daily Meeting data structure:"
        console.log "  - Meeting:", @scope.dailyMeeting
        console.log "  - Responses count:", @scope.dailyMeeting.responses?.length or 0
        
        # Ver estructura del primer usuario si existe
        if @scope.dailyMeeting.responses?.length > 0
            firstResponse = @scope.dailyMeeting.responses[0]
            console.log "  - First response user:", firstResponse.user
            if firstResponse.user
                console.log "  - User properties:", Object.keys(firstResponse.user)
                console.log "  - full_name_display:", firstResponse.user.full_name_display
                console.log "  - full_name:", firstResponse.user.full_name
                console.log "  - username:", firstResponse.user.username
                console.log "  - email:", firstResponse.user.email
                console.log "  - name:", firstResponse.user.name
                console.log "  - first_name:", firstResponse.user.first_name
                console.log "  - last_name:", firstResponse.user.last_name
                
                # Intentar mapear con activeUsers si el usuario no tiene nombre completo
                if not firstResponse.user.full_name_display and not firstResponse.user.full_name
                    userId = firstResponse.user.id or firstResponse.user
                    activeUser = _.find @scope.activeUsers, (u) -> u.id == userId
                    if activeUser
                        console.log "  - Mapped from activeUsers:", activeUser
                        # Enriquecer el objeto usuario con los datos de activeUsers
                        firstResponse.user.full_name_display = activeUser.full_name_display
                        firstResponse.user.full_name = activeUser.full_name
                        firstResponse.user.username = activeUser.username or firstResponse.user.username
        
        # Ver estructura de pending_members si existe
        if @scope.dailyMeeting.pending_members?.length > 0
            console.log "  - First pending member:", @scope.dailyMeeting.pending_members[0]
            if @scope.dailyMeeting.pending_members[0]
                console.log "  - Pending member properties:", Object.keys(@scope.dailyMeeting.pending_members[0])
        
        # Enriquecer todos los usuarios en las respuestas
        if @scope.dailyMeeting.responses and @scope.activeUsers
            for response in @scope.dailyMeeting.responses
                if response.user
                    # El usuario puede venir como objeto con solo id o como número directo
                    userId = if typeof response.user == 'object' then response.user.id else response.user
                    
                    activeUser = _.find @scope.activeUsers, (u) -> 
                        return parseInt(u.id) == parseInt(userId)
                    
                    if activeUser
                        console.log "Enriqueciendo usuario #{userId} con:", activeUser
                        # Crear un nuevo objeto usuario con todos los datos
                        response.user = {
                            id: userId
                            full_name_display: activeUser.full_name_display
                            full_name: activeUser.full_name
                            username: activeUser.username
                            email: activeUser.email
                            photo: activeUser.photo
                            big_photo: activeUser.big_photo
                            gravatar_id: activeUser.gravatar_id
                            color: activeUser.color
                            is_active: activeUser.is_active
                            role_name: activeUser.role_name
                        }
        
        # Enriquecer pending_members también
        if @scope.dailyMeeting.pending_members and @scope.activeUsers
            enrichedPendingMembers = []
            
            for member in @scope.dailyMeeting.pending_members
                # member puede ser solo un ID o un objeto
                memberId = if typeof member == 'object' then (member.id or member) else member
                
                activeUser = _.find @scope.activeUsers, (u) -> 
                    return parseInt(u.id) == parseInt(memberId)
                
                if activeUser
                    console.log "Enriqueciendo pending member #{memberId} con:", activeUser
                    enrichedPendingMembers.push(activeUser)
                else
                    # Si no encontramos el usuario, mantener el original
                    enrichedPendingMembers.push(member)
            
            @scope.dailyMeeting.pending_members = enrichedPendingMembers
        
        # Contar bloqueadores
        @scope.blockersCount = 0
        for response in @scope.dailyMeeting.responses or []
            if response.has_blockers
                @scope.blockersCount++

    checkMyResponse: ->
        return unless @scope.dailyMeeting and @scope.isDevelopmentTeam
        
        # Buscar mi respuesta en las respuestas del daily
        userId = @scope.user.id
        myResponse = _.find @scope.dailyMeeting.responses, (r) ->
            return r.user.id == userId
        
        if myResponse
            @scope.hasResponded = true
            @scope.myResponse = myResponse
            # Cargar la respuesta en el formulario por si quiere editar
            @scope.dailyResponse = {
                yesterday_work: myResponse.yesterday_work
                today_plan: myResponse.today_plan
                blockers: myResponse.blockers or ''
                mood: myResponse.mood
            }
        else
            @scope.hasResponded = false
            @scope.myResponse = null

    submitDailyResponse: ->
        return unless @scope.dailyMeeting and @scope.dailyResponse
    
        @scope.submitting = true
        
        # Asegurar que todos los campos tengan valor
        data = {
            yesterday_work: @scope.dailyResponse.yesterday_work or ""
            today_plan: @scope.dailyResponse.today_plan or ""
            blockers: @scope.dailyResponse.blockers or ""
            mood: @scope.dailyResponse.mood or "neutral"
        }
        
        console.log "Enviando respuesta:", data
        console.log "Meeting ID:", @scope.dailyMeeting.id
        
        promise = @rs.dailyMeetings.createResponse(@scope.dailyMeeting.id, data)
        
        promise.then (response) =>
            console.log "Respuesta exitosa:", response
            @scope.submitting = false
            @confirm.notify('success', null, 'Tu actualización diaria ha sido enviada exitosamente!')
            
            # Actualizar el daily meeting con la respuesta del servidor
            @scope.dailyMeeting = response
            @.processDailyMeeting()
            @.checkMyResponse()
            
        .catch (error) =>
            console.error "Error al enviar:", error
            @scope.submitting = false
            
            # Manejar diferentes tipos de errores
            if error.status == 403
                errorMsg = error.data?.error or "No tienes permisos para realizar esta acción"
            else if error.status == 400
                # Errores de validación
                if error.data?.yesterday_work
                    errorMsg = "Por favor completa qué hiciste ayer"
                else if error.data?.today_plan
                    errorMsg = "Por favor completa qué harás hoy"
                else
                    errorMsg = error.data?.error or "Error al enviar la respuesta"
            else
                errorMsg = "Error de conexión. Por favor intenta nuevamente"
                
            @confirm.notify('error', null, errorMsg)

    editResponse: ->
        @scope.hasResponded = false

    exportToExcel: ->
        return unless @scope.dailyMeeting
    
        console.log "Export clicked - Meeting ID:", @scope.dailyMeeting.id
        
        # Notificar inicio
        try
            @confirm.notify('info', null, 'Generando archivo Excel...')
        catch e
            console.log "Notificación no disponible"
        
        # Construir URL
        baseUrl = "/api/v1/daily-meetings/#{@scope.dailyMeeting.id}/export/"
        
        console.log "Export URL:", baseUrl
        
        # Obtener el token de autenticación
        token = @auth.getToken()
        
        # Usar fetch para descargar el archivo con autenticación
        fetch(baseUrl, {
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
            link.download = "daily_meeting_#{@scope.dailyMeeting.date}.xlsx"
            
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
                @confirm.notify('success', null, 'Descarga completada')
            catch e
                console.log "Notificación no disponible"
                
        .catch (error) =>
            console.error "Error al exportar:", error
            try
                @confirm.notify('error', null, 'Error al generar el archivo')
            catch e
                console.log "Notificación no disponible"

    refreshData: ->
        # Función para refrescar manualmente
        console.log "Refresh manual ejecutado"
        @.loadDailyMeeting()

    getMoodEmoji: (mood) ->
        moodOption = _.find @scope.moodOptions, (m) -> m.value == mood
        return moodOption?.emoji or '😐'

    getMoodText: (mood) ->
        moodOption = _.find @scope.moodOptions, (m) -> m.value == mood
        return @translate.instant(moodOption?.text or 'DAILY.MOOD_NEUTRAL')

    getMoodPercentage: (mood) ->
        total = @.getTotalResponses()
        return 0 if total == 0
        
        count = @scope.dailyMeeting?.team_mood_summary?[mood] or 0
        return (count / total) * 100

    getTotalResponses: ->
        return @scope.dailyMeeting?.participants_count or 0

    previousDay: ->
        currentDate = new Date(@scope.selectedDate)
        currentDate.setDate(currentDate.getDate() - 1)
        @scope.selectedDate = currentDate
        @.loadDailyMeeting()

    nextDay: ->
        return if @.isToday()
        currentDate = new Date(@scope.selectedDate)
        currentDate.setDate(currentDate.getDate() + 1)
        @scope.selectedDate = currentDate
        @.loadDailyMeeting()

    isToday: ->
        today = new Date()
        selected = new Date(@scope.selectedDate)
        return today.toDateString() == selected.toDateString()

    createTodayMeeting: ->
        return unless @scope.isScrumMaster
        
        @scope.loading = true
        
        # Buscar sprint activo
        activeSprint = _.find @scope.project.milestones, (m) ->
            return !m.closed
        
        data = {
            project: @scope.projectId
            date: new Date().toISOString().split('T')[0]
            sprint: activeSprint?.id
        }
        
        promise = @rs.dailyMeetings.create(data)
        
        promise.then (response) =>
            @confirm.notify('success', null, @translate.instant("DAILY.MEETING_CREATED"))
            @scope.dailyMeeting = response
            @scope.loading = false
            @.processDailyMeeting()
            
        .catch (error) =>
            @scope.loading = false
            errorMsg = error?.data?.error or @translate.instant("COMMON.ERROR")
            @confirm.notify('error', null, errorMsg)

    startAutoRefresh: ->
        # DESACTIVADO - No hacer nada
        return

module.controller("DailyScrumController", DailyScrumController)


#############################################################################
## Daily Scrum Menu Directive
#############################################################################

DailyScrumMenuDirective = ($translate) ->
    return {
        template: """
        <div class="daily-scrum-menu">
            <h3>{{ 'DAILY.MENU_TITLE' | translate }}</h3>
            
            <div class="menu-section" ng-if="isDevelopmentTeam">
                <h4>{{ 'DAILY.YOUR_STATUS' | translate }}</h4>
                <p ng-if="hasResponded" class="status-complete">
                    <tg-svg svg-icon="icon-check-circle"></tg-svg>
                    {{ 'DAILY.STATUS_COMPLETE' | translate }}
                </p>
                <p ng-if="!hasResponded" class="status-pending">
                    <tg-svg svg-icon="icon-clock"></tg-svg>
                    {{ 'DAILY.STATUS_PENDING' | translate }}
                </p>
            </div>
            
            <div class="menu-section" ng-if="dailyMeeting">
                <h4>{{ 'DAILY.TEAM_STATUS' | translate }}</h4>
                <div class="stats-list">
                    <div class="stat">
                        <span class="label">{{ 'DAILY.RESPONDED' | translate }}:</span>
                        <span class="value">{{ dailyMeeting.participants_count || 0 }}</span>
                    </div>
                    <div class="stat">
                        <span class="label">{{ 'DAILY.PENDING' | translate }}:</span>
                        <span class="value">{{ dailyMeeting.pending_members ? dailyMeeting.pending_members.length : 0 }}</span>
                    </div>
                    <div class="stat" ng-if="blockersCount > 0">
                        <span class="label">{{ 'DAILY.WITH_BLOCKERS' | translate }}:</span>
                        <span class="value blockers">{{ blockersCount }}</span>
                    </div>
                </div>
            </div>
        </div>
        """
        scope: false
    }

module.directive("tgDailyScrumMenu", ["$translate", DailyScrumMenuDirective])