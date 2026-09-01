###
# This source code is licensed under the terms of the
# GNU Affero General Public License found in the LICENSE file in
# the root directory of this source tree.
#
# Copyright (c) 2021-present Kaleidos INC
###

taiga = @.taiga

mixOf = @.taiga.mixOf

module = angular.module("taigaPlanningPoker")

#############################################################################
## Planning Poker Controller
#############################################################################

class PlanningPokerController extends mixOf(taiga.Controller, taiga.PageMixin)
    @.$inject = [
        "$scope",
        "$rootScope",
        "$tgRepo",
        "$tgResources",
        "$routeParams",
        "$q",
        "$location",
        "$tgNavUrls",
        "tgAppMetaService",
        "$tgAuth",
        "$translate",
        "tgProjectService",
        "tgErrorHandlingService",
        "$tgUserstoriesResourcesProvider",
        "$tgConfirm"
    ]

    constructor: (@scope, @rootscope, @repo, @rs, @params, @q, @location, @navUrls, @appMetaService, @auth,
                  @translate, @projectService, @errorHandlingService, userstoriesProvider,@confirm) ->

        @scope.sectionName = "PLANNING_POKER.SECTION_NAME"

        @userstoriesResource = userstoriesProvider(@rs)

        @scope.loadSessionUserStories = (sessionId) => @.loadSessionUserStories(sessionId)

        @scope.selectedStoryForMembers = null
        @scope.sessionId = null

        @scope.currentEstimations = {}
        @scope.estimationValue = null

        # Función para establecer el valor de estimación directamente
        @scope.setEstimationValue = (value) =>
            @scope.estimationValue = value
            @scope.$apply() if not @scope.$$phase

        # Función para iniciar polling de estimaciones
        startEstimationPolling = =>
            if @scope.estimationPollingInterval
                clearInterval(@scope.estimationPollingInterval)
            
            # Polling cada 2 segundos mientras haya una historia seleccionada
            @scope.estimationPollingInterval = setInterval =>
                if @scope.selectedStoryForMembers and @scope.sessionId
                    @.loadEstimations()
                else
                    clearInterval(@scope.estimationPollingInterval)
                    @scope.estimationPollingInterval = null
            , 2000

        # Detener polling cuando se destruya el scope
        @scope.$on '$destroy', =>
            if @scope.estimationPollingInterval
                clearInterval(@scope.estimationPollingInterval)

        # Definir sendEstimation en el scope
        @scope.sendEstimation = =>
            if not @scope.sessionId
                @confirm.notify('error', null, null, "Debes seleccionar una sesión primero")
                return
                
            if not @scope.selectedStory
                @confirm.notify('error', null, null, "Debes seleccionar una historia primero")
                return
                
            if not @scope.estimationValue? or @scope.estimationValue is null
                @confirm.notify('error', null, null, "Debes seleccionar un valor de estimación")
                return
            
            # Validar Fibonacci
            fibonacciValues = [0, 1, 2, 3, 5, 8, 13, 20, 40, 100]
            estimationInt = parseInt(@scope.estimationValue)
            
            if estimationInt not in fibonacciValues
                @confirm.notify('error', null, null, "La estimación debe ser un valor de Fibonacci: 0, 1, 2, 3, 5, 8, 13, 20, 40, 100")
                return
            
            # Preparar datos
            data = {
                session: parseInt(@scope.sessionId)
                user_story: @scope.selectedStory.id
                user: @auth.getUser().id
                estimation_value: estimationInt
            }
            
            # Crear la estimación usando el servicio de recursos
            promise = null
            
            if @rs.estimations?.create
                promise = @rs.estimations.create(data)
            else if @rs.http
                url = "/api/v1/planning-poker/estimations/"
                promise = @rs.http.post(url, data)
            else
                @confirm.notify('error', null, null, "Error: Servicio no disponible")
                return
            
            promise.then (response) =>
                # Obtener el ID del usuario actual
                userId = @auth.getUser().id
                
                # Actualizar currentEstimations inmediatamente
                @scope.currentEstimations[@scope.selectedStory.id] = estimationInt
                
                # Actualizar estimationsByUser inmediatamente si es la historia seleccionada
                if @scope.selectedStoryForMembers?.id == @scope.selectedStory.id
                    @scope.estimationsByUser = @scope.estimationsByUser or {}
                    @scope.estimationsByUser[String(userId)] = estimationInt
                
                # Limpiar el campo
                @scope.estimationValue = null
                
                # Forzar actualización visual
                @scope.$apply() if not @scope.$$phase
                
                # Emitir evento
                @rootscope.$broadcast 'estimation:updated', {
                    session: @scope.sessionId
                    user_story: @scope.selectedStory.id
                    user: userId
                    value: estimationInt
                }
                
                # Recargar todas las estimaciones inmediatamente
                setTimeout =>
                    @.loadEstimations()
                , 500
                
                # Iniciar polling temporal para asegurar sincronización
                startEstimationPolling()
                
                # Detener polling después de 10 segundos
                setTimeout =>
                    if @scope.estimationPollingInterval
                        clearInterval(@scope.estimationPollingInterval)
                        @scope.estimationPollingInterval = null
                , 10000
                
            .catch (error) =>
                errorMsg = error?.data?.error or error?.data?._error_message or "Error al enviar la estimación"
                @confirm.notify('error', null, null, errorMsg)
        
        # Exponer sendEstimation en el scope
        @scope.exportToExcel = =>
            @.exportToExcel()

        @scope.canExport = =>
            # Verificar si hay una sesión seleccionada
            return @scope.sessionId? and @scope.sessionId != null

        # Método para cambiar de sesión manualmente
        @scope.changeSession = (sessionId) =>
            if not sessionId
                return
                
            sessionIdNum = parseInt(sessionId)
            
            # Forzar actualización del sessionId
            @scope.sessionId = sessionIdNum
            
            # Guardar en localStorage
            if @scope.projectId
                savedSessionKey = "planningPoker_session_#{@scope.projectId}"
                localStorage.setItem(savedSessionKey, sessionIdNum)
            
            # Limpiar todos los datos de la sesión anterior
            @scope.selectedStory = null
            @scope.selectedStoryForMembers = null
            @scope.estimationsByUser = {}
            @scope.currentEstimations = {}
            @scope.hasConsensus = false
            @scope.consensusValue = null
            @scope.allVoted = false
            @scope.sessionUserStories = []
            @scope.missingVotes = 0
            @scope.totalVoters = 0
            @scope.votedCount = 0
            @scope.missingUsersNames = null
            @scope.differentValues = []
            @scope.allEstimationsByStory = {}
            
            # Cargar nuevas historias
            @.loadSessionUserStories(sessionIdNum)
            
            # Cargar estimaciones con delay
            setTimeout =>
                @.loadCurrentUserEstimations()
            , 500
            
            # Forzar actualización del scope
            @scope.$evalAsync()

        # Watchers
        @scope.$watch "sessionId", (newVal, oldVal) =>
            if newVal? and newVal != oldVal
                # Asegurar que newVal sea número
                newValNum = parseInt(newVal)
                if newValNum != @scope.sessionId
                    @scope.sessionId = newValNum
                
                # Limpiar localStorage y datos al cambiar de sesión
                if oldVal and @scope.projectId
                    oldStoryKey = "planningPoker_selectedStory_#{@scope.projectId}_#{oldVal}"
                    localStorage.removeItem(oldStoryKey)
                
                # Guardar nueva sesión en localStorage
                savedSessionKey = "planningPoker_session_#{@scope.projectId}"
                localStorage.setItem(savedSessionKey, newVal)
                
                # LIMPIAR COMPLETAMENTE todos los datos de la sesión anterior
                @scope.selectedStory = null
                @scope.selectedStoryForMembers = null
                @scope.estimationsByUser = {}
                @scope.currentEstimations = {}
                @scope.hasConsensus = false
                @scope.consensusValue = null
                @scope.allVoted = false
                @scope.sessionUserStories = []
                @scope.missingVotes = 0
                @scope.totalVoters = 0
                @scope.votedCount = 0
                @scope.missingUsersNames = null
                @scope.differentValues = []
                @scope.allEstimationsByStory = {}
                
                # Cargar nuevas historias y estimaciones
                @.loadSessionUserStories(newVal)
                
                # Usar timeout para asegurar que las historias se carguen primero
                setTimeout =>
                    @.loadCurrentUserEstimations()
                , 300
                
                # Forzar actualización del scope
                @scope.$evalAsync()
            else if not newVal?
                # Si no hay sesión, limpiar todo
                @scope.sessionUserStories = []
                @scope.estimationsByUser = {}
                @scope.currentEstimations = {}
                @scope.selectedStory = null
                @scope.selectedStoryForMembers = null
                @scope.allEstimationsByStory = {}

        # Watcher para selectedStory (historia del usuario actual)
        @scope.$watch "selectedStory", (newVal, oldVal) =>
            if newVal
                # Sincronizar con selectedStoryForMembers si es diferente
                if @scope.selectedStoryForMembers?.id != newVal.id
                    @scope.selectedStoryForMembers = newVal
                
                # Para roles observadores, cargar estimaciones inmediatamente
                observerRoles = ['Product Owner', 'Scrum Master', 'Stakeholder']
                if @scope.currentUser?.role_name in observerRoles
                    # Pequeño delay para asegurar sincronización
                    setTimeout =>
                        @.loadEstimations()
                    , 100

        # Watcher para selectedStoryForMembers
        @scope.$watch "selectedStoryForMembers", (newVal, oldVal) =>
            if newVal
                # Guardar en localStorage solo si tenemos sesión
                if @scope.sessionId and @scope.projectId
                    savedStoryKey = "planningPoker_selectedStory_#{@scope.projectId}_#{@scope.sessionId}"
                    localStorage.setItem(savedStoryKey, newVal.id)
                
                # LIMPIAR estimaciones si cambió la historia
                if oldVal and oldVal.id != newVal.id
                    @scope.estimationsByUser = {}
                    @scope.hasConsensus = false
                    @scope.consensusValue = null
                    @scope.allVoted = false
                    @scope.differentValues = []
                    @scope.missingVotes = 0
                    @scope.missingUsersNames = null
                
                # Sincronizar con selectedStory si es necesario
                matchingStory = _.find @scope.sessionUserStories, (s) -> s.id == newVal.id
                if matchingStory and @scope.selectedStory?.id != matchingStory.id
                    @scope.selectedStory = matchingStory
                
                # Para roles observadores, verificar si ya tenemos las estimaciones cargadas
                observerRoles = ['Product Owner', 'Scrum Master', 'Stakeholder']
                if @scope.currentUser?.role_name in observerRoles and @scope.allEstimationsByStory?[newVal.id]
                    # Usar las estimaciones ya cargadas
                    @scope.estimationsByUser = @scope.allEstimationsByStory[newVal.id] or {}
                    @.calculateMissingVotes()
                    @.checkConsensus()
                else
                    # Cargar estimaciones normalmente
                    @.loadEstimations()
            else
                # Solo limpiar si realmente se deseleccionó
                if oldVal
                    @scope.estimationsByUser = {}
                    @scope.hasConsensus = false
                    @scope.consensusValue = null
                    @scope.allVoted = false
                    @scope.differentValues = []
                    # Limpiar localStorage
                    if @scope.sessionId and @scope.projectId
                        savedStoryKey = "planningPoker_selectedStory_#{@scope.projectId}_#{@scope.sessionId}"
                        localStorage.removeItem(savedStoryKey)

        # Listener para nuevas sesiones
        @scope.$on 'planningform:new:success', (event, newSession) =>
            if not newSession
                return
                
            sessionData = null
            if newSession._attrs
                sessionData = newSession._attrs
            else if newSession.id
                sessionData = newSession
            else
                return
            
            @scope.sessions = @scope.sessions or []
            
            formattedSession = {
                id: sessionData.id
                name: sessionData.name or "Sesión " + sessionData.id
                description: sessionData.description or ""
                user_stories: sessionData.user_stories or []
                project: sessionData.project
            }
            
            @scope.sessions.unshift(formattedSession)
            
            # Notificar que se creó la sesión
            @confirm.notify('success', null, null, "Sesión creada exitosamente")
            
            @scope.$evalAsync()

        # Listener para actualización de estimaciones desde otros componentes
        @scope.$on 'estimation:updated', (event, data) =>
            if data.session == @scope.sessionId and data.user_story == @scope.selectedStoryForMembers?.id
                # Recargar estimaciones
                @.loadEstimations()

        # Método para refrescar manualmente
        @scope.refreshEstimations = =>
            if @scope.selectedStoryForMembers
                @.loadEstimations()

        # Exponer loadEstimations directamente en el scope para el botón
        @scope.loadEstimations = =>
            @.loadEstimations()

        # Auto-refresh opcional cada 5 segundos cuando hay una historia seleccionada
        @scope.enableAutoRefresh = false
        @scope.autoRefreshInterval = null
        
        @scope.toggleAutoRefresh = =>
            @scope.enableAutoRefresh = not @scope.enableAutoRefresh
            
            if @scope.enableAutoRefresh
                @scope.autoRefreshInterval = setInterval =>
                    if @scope.selectedStoryForMembers
                        @.loadEstimations()
                , 5000
            else
                if @scope.autoRefreshInterval
                    clearInterval(@scope.autoRefreshInterval)
                    @scope.autoRefreshInterval = null
        
        # Limpiar intervalos cuando se destruya el scope
        @scope.$on '$destroy', =>
            if @scope.autoRefreshInterval
                clearInterval(@scope.autoRefreshInterval)
            if @scope.estimationPollingInterval
                clearInterval(@scope.estimationPollingInterval)

        # Inicializar el mapa de estimaciones
        @scope.estimationsByUser = {}
        @scope.currentEstimations = {}
        @scope.allEstimationsByStory = {}

        promise = @.loadInitialData()

        # On Success
        promise.then =>
            title = @translate.instant("PLANNING_POKER.PAGE_TITLE", {projectName: @scope.project.name})
            description = @translate.instant("PLANNING_POKER.PAGE_DESCRIPTION", {
                projectName: @scope.project.name,
                projectDescription: @scope.project.description
            })
            @appMetaService.setAll(title, description)

        # On Error
        promise.then null, @.onInitialDataError.bind(@)

    loadEstimations: ->
        return unless @scope.sessionId and @scope.selectedStoryForMembers
        
        # Evitar múltiples llamadas simultáneas
        if @_loadingEstimations
            return
            
        @_loadingEstimations = true
        
        filters = {
            session: @scope.sessionId
            user_story: @scope.selectedStoryForMembers.id
        }
        
        promise = null
        
        if @rs.estimations?.list
            promise = @rs.estimations.list(filters)
        else if @rs.http
            url = "/api/v1/planning-poker/estimations/?session=#{filters.session}&user_story=#{filters.user_story}"
            promise = @rs.http.get(url)
        else
            @_loadingEstimations = false
            return
        
        promise.then (response) =>
            # Procesar la respuesta
            estimations = []
            
            # La respuesta puede venir en diferentes formatos
            if response?.data
                if angular.isArray(response.data)
                    estimations = response.data
                else if response.data._attrs and angular.isArray(response.data._attrs)
                    estimations = response.data._attrs
                else if response.data.results and angular.isArray(response.data.results)
                    estimations = response.data.results
            else if response?._attrs and angular.isArray(response._attrs)
                estimations = response._attrs
            else if angular.isArray(response)
                estimations = response
            
            # Limpiar y reconstruir el mapa de estimaciones
            @scope.estimationsByUser = {}
            
            # Procesar TODAS las estimaciones
            for estimation in estimations
                estimationData = null
                if estimation._attrs
                    estimationData = estimation._attrs
                else if estimation.user and estimation.estimation_value?
                    estimationData = estimation
                else
                    continue
                
                if estimationData and estimationData.user and estimationData.estimation_value?
                    userId = String(estimationData.user)
                    @scope.estimationsByUser[userId] = estimationData.estimation_value
            
            # Calcular cuántos faltan por votar
            @.calculateMissingVotes()
            
            # Verificar consenso
            @.checkConsensus()
            
            # Marcar como no cargando
            @_loadingEstimations = false
            
            # Forzar actualización del scope
            if not @scope.$$phase
                @scope.$apply()
            
        .catch (error) =>
            @scope.estimationsByUser = {}
            @_loadingEstimations = false
            if not @scope.$$phase
                @scope.$apply()

    calculateMissingVotes: ->
        return unless @scope.selectedStoryForMembers
        
        # Roles que NO pueden votar (igual que en el backend)
        nonVotingRoles = ['Product Owner', 'Scrum Master', 'Stakeholder']
        
        # Obtener todos los miembros del proyecto
        allMembers = @scope.activeUsers or []
        
        # Filtrar usuarios que SÍ pueden votar
        votingUsers = _.filter allMembers, (user) ->
            user and user.role_name and user.role_name not in nonVotingRoles
        
        totalVoters = votingUsers.length
        
        # Contar cuántos ya votaron
        votedCount = Object.keys(@scope.estimationsByUser or {}).length
        
        # Calcular cuántos faltan
        @scope.missingVotes = Math.max(0, totalVoters - votedCount)
        @scope.totalVoters = totalVoters
        @scope.votedCount = votedCount
        
        # Identificar quiénes faltan específicamente
        if @scope.missingVotes > 0
            votedUserIds = Object.keys(@scope.estimationsByUser or {}).map (id) -> String(id)
            missingUsers = _.filter votingUsers, (user) ->
                String(user.id) not in votedUserIds
            
            missingNames = _.map(missingUsers, 'full_name_display').join(', ')
            @scope.missingUsersNames = missingNames
        else
            @scope.missingUsersNames = null

    checkConsensus: ->
        return unless @scope.estimationsByUser and @scope.selectedStoryForMembers
        
        estimationValues = _.values(@scope.estimationsByUser)
        
        # Si no hay estimaciones, no hay consenso
        if estimationValues.length == 0
            @scope.hasConsensus = false
            @scope.consensusValue = null
            @scope.differentValues = []
            @scope.allVoted = false
            return
        
        # Verificar si todos votaron
        if @scope.missingVotes > 0
            @scope.hasConsensus = false
            @scope.consensusValue = null
            @scope.differentValues = []
            @scope.allVoted = false
            return
        
        # Todos votaron
        @scope.allVoted = true
        
        # Verificar si todos tienen el mismo valor
        uniqueValues = _.uniq(estimationValues)
        
        if uniqueValues.length == 1
            @scope.hasConsensus = true
            @scope.consensusValue = uniqueValues[0]
            @scope.differentValues = []
        else
            @scope.hasConsensus = false
            @scope.consensusValue = null
            @scope.differentValues = uniqueValues.sort((a, b) -> a - b)
        
        # Forzar actualización del scope
        @scope.$apply() if not @scope.$$phase

    loadCurrentUserEstimations: ->
        return unless @scope.sessionId
        
        # Solo cargar estimaciones del usuario actual si NO es un rol observador
        observerRoles = ['Product Owner', 'Scrum Master', 'Stakeholder']
        if @scope.currentUser?.role_name in observerRoles
            # Para roles observadores, cargar TODAS las estimaciones de TODOS los usuarios
            @.loadAllSessionEstimations()
            return
        
        userId = @auth.getUser().id
        # Asegurar que sessionId sea número
        sessionIdNum = parseInt(@scope.sessionId)
        
        filters = {
            session: sessionIdNum
            user: userId
        }
        
        promise = null

        if @rs.estimations?.list
            promise = @rs.estimations.list(filters)
        else if @rs.http
            url = "/api/v1/planning-poker/estimations/?session=#{filters.session}&user=#{filters.user}"
            promise = @rs.http.get(url)
        else
            return
        
        promise.then (response) =>
            # Procesar la respuesta
            estimations = []
            
            if response?.data
                if angular.isArray(response.data)
                    estimations = response.data
                else if response.data._attrs and angular.isArray(response.data._attrs)
                    estimations = response.data._attrs
            else if response?._attrs and angular.isArray(response._attrs)
                estimations = response._attrs
            else if angular.isArray(response)
                estimations = response

            # LIMPIAR antes de reconstruir
            @scope.currentEstimations = {}
            
            for estimation in estimations
                estimationData = estimation._attrs or estimation
                
                if estimationData.user_story and estimationData.estimation_value?
                    @scope.currentEstimations[estimationData.user_story] = estimationData.estimation_value
                    
                    # Si esta es la historia seleccionada, actualizar también estimationsByUser
                    if @scope.selectedStoryForMembers?.id == estimationData.user_story
                        @scope.estimationsByUser = @scope.estimationsByUser or {}
                        @scope.estimationsByUser[String(userId)] = estimationData.estimation_value
            
            # Forzar actualización del scope
            @scope.$evalAsync()
            
        .catch (error) =>
            # Silencioso
    
    # Nuevo método para cargar TODAS las estimaciones de una sesión (para PO, SM, Stakeholder)
    loadAllSessionEstimations: ->
        return unless @scope.sessionId
        
        filters = {
            session: @scope.sessionId
        }
        
        promise = null
        
        if @rs.estimations?.list
            promise = @rs.estimations.list(filters)
        else if @rs.http
            url = "/api/v1/planning-poker/estimations/?session=#{filters.session}"
            promise = @rs.http.get(url)
        else
            return
        
        promise.then (response) =>
            # Procesar la respuesta
            estimations = []
            
            if response?.data
                if angular.isArray(response.data)
                    estimations = response.data
                else if response.data._attrs and angular.isArray(response.data._attrs)
                    estimations = response.data._attrs
            else if response?._attrs and angular.isArray(response._attrs)
                estimations = response._attrs
            else if angular.isArray(response)
                estimations = response
            
            # Crear un mapa de estimaciones por historia
            estimationsByStory = {}
            
            for estimation in estimations
                estimationData = estimation._attrs or estimation
                
                if estimationData.user_story and estimationData.estimation_value?
                    storyId = estimationData.user_story
                    userId = String(estimationData.user)
                    
                    if not estimationsByStory[storyId]
                        estimationsByStory[storyId] = {}
                    
                    estimationsByStory[storyId][userId] = estimationData.estimation_value
            
            # Guardar las estimaciones por historia
            @scope.allEstimationsByStory = estimationsByStory
            
            # Si hay una historia seleccionada, actualizar estimationsByUser
            if @scope.selectedStoryForMembers?.id
                @scope.estimationsByUser = estimationsByStory[@scope.selectedStoryForMembers.id] or {}
                @.calculateMissingVotes()
                @.checkConsensus()
            
            # Forzar actualización del scope
            @scope.$evalAsync()
            
        .catch (error) =>
            # Silencioso

    setRole: (role) ->
        if role
            @scope.filtersRole = role
        else
            @scope.filtersRole = null

    loadMembers: ->
        user = @auth.getUser()
        userId = parseInt(user?.id)

        # Inicializar selectedStory
        @scope.selectedStory = null  
        @scope.sectionName = "PLANNING_POKER.SECTION_NAME"

        @scope.setSelectedStory = (story) =>
            @$scope.selectedStory = story

        # Calculate totals
        @scope.totals = {}
        for member in @scope.activeUsers
            @scope.totals[member.id] = 0

        # Get current user
        @scope.currentUser = _.find(@scope.activeUsers, (m) -> parseInt(m.id) == userId)

        # Get member list without current user
        @scope.memberships = _.reject(@scope.activeUsers, (m) -> parseInt(m.id) == userId)

    loadProject: ->
        project = @projectService.project.toJS()

        @scope.projectId = project.id
        @scope.project = project
        @scope.$emit('project:loaded', project)

        @scope.issuesEnabled = project.is_issues_activated
        @scope.tasksEnabled = project.is_kanban_activated or project.is_backlog_activated
        @scope.wikiEnabled = project.is_wiki_activated
        @scope.owner = project.owner.id

        return project

    loadSessions: ->
        projectId = @scope.project.id

        # Intentar recuperar la sesión guardada en localStorage
        savedSessionKey = "planningPoker_session_#{projectId}"
        savedSessionId = parseInt(localStorage.getItem(savedSessionKey))

        @rs.planningSessions.list(projectId).then (res) =>
            cleaned = []

            for item in res
                sessionData = null
                
                if item?._attrs? and angular.isArray(item._attrs)
                    for sesion in item._attrs
                        if sesion.id?
                            cleaned.push(sesion)
                else if item?._attrs? and item._attrs.id?
                    cleaned.push(item._attrs)
                else if item?.id?
                    cleaned.push(item)

            @scope.sessions = cleaned

            # Verificar si la sesión guardada existe
            if savedSessionId
                savedSessionExists = _.find cleaned, (s) -> s.id == savedSessionId
                if savedSessionExists
                    @scope.sessionId = savedSessionId
            
            # Si no hay sesión seleccionada y hay sesiones disponibles
            if not @scope.sessionId and cleaned.length > 0
                @scope.sessionId = cleaned[0].id
            
            # Si hay una sesión seleccionada, guardarla
            if @scope.sessionId
                localStorage.setItem(savedSessionKey, @scope.sessionId)
                # Cargar historias de la sesión con un pequeño delay
                setTimeout =>
                    @.loadSessionUserStories(@scope.sessionId)
                    # Cargar estimaciones del usuario actual
                    @.loadCurrentUserEstimations()
                , 200

    loadMemberStats: ->
        return @rs.projects.memberStats(@scope.projectId).then (stats) =>
          totals = {}
          _.forEach @scope.totals, (total, userId) =>
              vals = _.map(stats, (memberStats, statsKey) -> memberStats[userId])
              total = _.reduce(vals, (sum, el) -> sum + el)
              @scope.totals[userId] = total

          @scope.stats = @._processStats(stats)
          @scope.stats.totals = @scope.totals

    _processStat: (stat) ->
        max = _.max(_.toArray(stat))
        min = _.min(_.toArray(stat))

        singleStat = Object()
        for own key, value of stat
            if value == min
                singleStat[key] = 0.1
            else if value == max
                singleStat[key] = 1
            else
                singleStat[key] = (value * 0.5) / max

        return singleStat

    _processStats: (stats) ->
        for key,value of stats
            stats[key] = @._processStat(value)
        return stats

    loadUserStories: ->
        @userstoriesResource.listAll(@scope.projectId, {}).then (stories) =>
            @scope.userstories = stories

    loadSessionUserStories: (sessionId) ->
        # Asegurar que sessionId sea un número
        sessionIdNum = parseInt(sessionId)

        # Actualizar el sessionId en el scope si es diferente
        if sessionIdNum and sessionIdNum != @scope.sessionId
            @scope.sessionId = sessionIdNum
        
        # Encuentra la sesión seleccionada
        selectedSession = _.find @scope.sessions, (s) -> 
            return s.id == sessionIdNum
        
        if selectedSession and selectedSession.user_stories and selectedSession.user_stories.length > 0
            # Filtrar las historias que pertenecen a esta sesión
            sessionStoryIds = selectedSession.user_stories
            
            @scope.sessionUserStories = _.filter @scope.userstories, (story) ->
                return sessionStoryIds.indexOf(story.id) >= 0
        else
            @scope.sessionUserStories = []
        
        # Limpiar COMPLETAMENTE todo al cambiar de sesión
        @scope.selectedStory = null
        @scope.selectedStoryForMembers = null
        @scope.estimationsByUser = {}
        @scope.currentEstimations = {}
        @scope.hasConsensus = false
        @scope.consensusValue = null
        @scope.missingVotes = 0
        @scope.allVoted = false
        @scope.differentValues = []
        @scope.totalVoters = 0
        @scope.votedCount = 0
        @scope.missingUsersNames = null
        
        # Forzar actualización del scope
        @scope.$evalAsync()
        
        # Broadcast para notificar el cambio
        @scope.$broadcast('session:stories:updated', @scope.sessionUserStories)
        
        # Cargar las estimaciones del usuario actual para esta sesión
        if sessionId
            # Usar timeout para asegurar que todo se haya limpiado
            setTimeout =>
                @.loadCurrentUserEstimations()
                
                # Si hay una historia guardada en localStorage, recuperarla
                if @scope.projectId
                    savedStoryKey = "planningPoker_selectedStory_#{@scope.projectId}_#{sessionId}"
                    savedStoryId = parseInt(localStorage.getItem(savedStoryKey))
                    
                    if savedStoryId and @scope.sessionUserStories.length > 0
                        savedStory = _.find @scope.sessionUserStories, (s) -> s.id == savedStoryId
                        if savedStory
                            @scope.selectedStoryForMembers = savedStory
                            @scope.selectedStory = savedStory
                            
                            # Cargar estimaciones de esta historia con otro timeout
                            setTimeout =>
                                @.loadEstimations()
                            , 300
            , 200

    loadInitialData: ->
        project = @.loadProject()

        @.fillUsersAndRoles(project.members, project.roles)
        @scope.activeUsers = angular.copy(@scope.users)

        @.loadMembers()

        user = @auth.getUser()
        @scope.currentUser = _.find(@scope.activeUsers, {id: user?.id})
        @scope.memberships = _.reject(@scope.activeUsers, {id: user?.id})

        userRoles = _.map @scope.users, (user) -> user.role

        @scope.roles = _.filter @scope.roles, (role) -> userRoles.indexOf(role.id) != -1

        # Inicializar variables
        @scope.sessionUserStories = []
        @scope.estimationsByUser = {}
        @scope.currentEstimations = {}
        @scope.missingVotes = 0
        @scope.totalVoters = 0
        @scope.votedCount = 0
        @scope.hasConsensus = false
        @scope.consensusValue = null
        @scope.missingUsersNames = null
        @scope.allVoted = false
        @scope.differentValues = []

        return @.loadMemberStats().then =>
            # Primero cargar las historias
            return @.loadUserStories()
        .then =>
            # Después cargar las sesiones
            return @.loadSessions()

    exportToExcel: ->
        return unless @scope.sessionId
        
        # Asegurar que tenemos un sessionId válido
        sessionId = parseInt(@scope.sessionId)
        
        if not sessionId
            @confirm.notify('error', null, null, "Debes seleccionar una sesión primero")
            return
    
        # Mostrar indicador de carga
        @confirm.notify('success', null, null, "Generando archivo Excel para sesión #{sessionId}...")
        
        # URL del endpoint - Ajustada para Taiga
        url = "/api/v1/planning-poker/planning-sessions/#{@scope.sessionId}/export_excel/"
        
        # Crear un elemento anchor temporal para descargar
        downloadLink = document.createElement('a')
        downloadLink.style.display = 'none'
        document.body.appendChild(downloadLink)
        
        # Hacer la petición con el token de autenticación
        authToken = @auth.getToken()
        
        # Usar XMLHttpRequest para manejar la descarga de archivos binarios
        xhr = new XMLHttpRequest()
        xhr.open('GET', url, true)
        xhr.setRequestHeader('Authorization', "Bearer #{authToken}")
        xhr.setRequestHeader('x-disable-pagination', 'true')  # Importante para Taiga
        xhr.responseType = 'blob'
        
        xhr.onload = =>
            if xhr.status == 200
                # Crear un blob URL para el archivo
                blob = xhr.response
                blobUrl = window.URL.createObjectURL(blob)
                
                # Obtener el nombre del archivo del header si está disponible
                contentDisposition = xhr.getResponseHeader('Content-Disposition')
                filename = 'planning_poker_export.xlsx'
                
                if contentDisposition
                    filenameMatch = contentDisposition.match(/filename="(.+)"/)
                    if filenameMatch and filenameMatch[1]
                        filename = filenameMatch[1]
                
                # Configurar y hacer clic en el enlace de descarga
                downloadLink.href = blobUrl
                downloadLink.download = filename
                downloadLink.click()
                
                # Limpiar
                window.URL.revokeObjectURL(blobUrl)
                document.body.removeChild(downloadLink)
                
                @confirm.notify('success', null, null, "Archivo Excel generado exitosamente")
            else
                try
                    # Intentar leer el error del response
                    reader = new FileReader()
                    reader.onload = =>
                        try
                            errorData = JSON.parse(reader.result)
                            errorMsg = errorData.error or "Error al generar el archivo"
                            @confirm.notify('error', null, null, errorMsg)
                        catch
                            @confirm.notify('error', null, null, "Error al generar el archivo Excel")
                    reader.readAsText(xhr.response)
                catch
                    @confirm.notify('error', null, null, "Error al generar el archivo Excel")
        
        xhr.onerror = =>
            @confirm.notify('error', null, null, "Error de conexión al generar el archivo")
        
        xhr.send()

module.controller("PlanningPokerController", PlanningPokerController)


#############################################################################
## PLANNING_POKER Filters Directive
#############################################################################

PlanningPokerFiltersDirective = () ->
    return {
        templateUrl: "planningpoker/planningpoker-filter.html",
    }

module.directive("tgPlanningPokerFilters", [PlanningPokerFiltersDirective])


#############################################################################
## PlanningPoker Member Stats Directive
#############################################################################

PlanningPokerMemberStatsDirective = () ->
    return {
        templateUrl: "planningpoker/planningpoker-member-stats.html",
        scope: {
            stats: "=",
            userId: "=user"
            issuesEnabled: "=issuesenabled"
            tasksEnabled: "=tasksenabled"
            wikiEnabled: "=wikienabled"
        }
    }

module.directive("tgPlanningPokerMemberStats", PlanningPokerMemberStatsDirective)


#############################################################################
## PlanningPoker Current User Directive
#############################################################################

PlanningPokerMemberCurrentUserDirective = () ->
    return {
        restrict: "E"
        templateUrl: "planningpoker/planningpoker-member-current-user.html"
        scope: false  # Compartir scope con el controlador padre
    }

module.directive("tgPlanningPokerCurrentUser", PlanningPokerMemberCurrentUserDirective)


#############################################################################
## PlanningPoker Members Directive
#############################################################################

PlanningPokerMembersDirective = () ->
    template = "planningpoker/planningpoker-members.html"

    return {
        templateUrl: template,
        scope: false  # Usamos el mismo $scope del padre
    }

module.directive("tgPlanningPokerMembers", PlanningPokerMembersDirective)


#############################################################################
## Leave project Directive
#############################################################################

LeavePokerDirective = ($repo, $confirm, $location, $rs, $navurls, $translate, lightboxFactory, currentUserService) ->
    link = ($scope, $el, $attrs) ->
        leaveConfirm = () ->
            leave_project_text = $translate.instant("PLANNING_POKER.ACTION_LEAVE_PROJECT")
            confirm_leave_project_text = $translate.instant("PLANNING_POKER.CONFIRM_LEAVE_PROJECT")

            $confirm.ask(leave_project_text, confirm_leave_project_text).then (response) =>
                promise = $rs.projects.leave($scope.project.id)

                promise.then =>
                    currentUserService.loadProjects().then () ->
                        response.finish()
                        $confirm.notify("success")
                        $location.path($navurls.resolve("home"))

                promise.then null, (response) ->
                    response.finish()
                    $confirm.notify('error', response.data._error_message)

        $scope.leave = () ->
            if $scope.project.owner.id == $scope.user.id
                lightboxFactory.create("tg-lightbox-leave-poker-warning", {
                    class: "lightbox lightbox-leave-poker-warning"
                }, {
                    isCurrentUser: true,
                    project: $scope.project
                })
            else
                leaveConfirm()

    return {
        scope: {
            user: "=",
            project: "="
        },
        templateUrl: "planningpoker/leave-poker.html",
        link: link
    }

module.directive("tgLeavePoker", ["$tgRepo", "$tgConfirm", "$tgLocation", "$tgResources", "$tgNavUrls", "$translate", "tgLightboxFactory", "tgCurrentUserService",
                                    LeavePokerDirective])


#############################################################################
## PlanningPoker Filters
#############################################################################

membersFilter = ->
    return (members, filtersQ, filtersRole) ->
        return _.filter members, (m) -> (not filtersRole or m.role == filtersRole.id) and
                                        (not filtersQ or m.full_name.search(new RegExp(filtersQ, "i")) >= 0)

module.filter('membersFilter', membersFilter)