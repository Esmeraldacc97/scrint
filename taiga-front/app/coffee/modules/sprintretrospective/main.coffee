###
# Sprint Retrospective Controller
###

taiga = @.taiga
mixOf = @.taiga.mixOf

module = angular.module("taigaSprintRetrospective")

#############################################################################
## Sprint Retrospective Controller
#############################################################################

class SprintRetrospectiveController extends mixOf(taiga.Controller, taiga.PageMixin)
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

        @scope.sectionName = "SPRINT_RETROSPECTIVE.SECTION_NAME"
        
        # Initialize variables
        @scope.selectedSprintId = null
        @scope.sprintData = null
        @scope.retrospective = null
        @scope.teamMembers = []
        @scope.previousActions = []
        @scope.submitting = false
        @scope.loading = true
        @scope.error = null
        @scope.activeTab = 'whatWentWell'
        @scope.voting = {}
        @scope.hasVoted = {}
        
        # Initialize retrospective form
        @scope.retrospectiveForm = {
            went_well: []
            to_improve: []
            action_items: []
            team_mood: 'neutral'
            previous_actions_completed: []
        }
        
        # Options
        @scope.moodOptions = [
            {value: 'terrible', text: 'SPRINT_RETROSPECTIVE.MOOD_TERRIBLE', emoji: '😞'},
            {value: 'bad', text: 'SPRINT_RETROSPECTIVE.MOOD_BAD', emoji: '😕'},
            {value: 'neutral', text: 'SPRINT_RETROSPECTIVE.MOOD_NEUTRAL', emoji: '😐'},
            {value: 'good', text: 'SPRINT_RETROSPECTIVE.MOOD_GOOD', emoji: '🙂'},
            {value: 'great', text: 'SPRINT_RETROSPECTIVE.MOOD_GREAT', emoji: '😊'}
        ]
        
        # Temporary items for adding
        @scope.forms = {
            newWentWell: ''
            newToImprove: ''
            newAction: {
                action: ''
                responsible_id: null
                due_date: null
            }
        }
        
        # Bind all functions to scope
        @scope.loadSprintRetrospective = => @.loadSprintRetrospective()
        @scope.submitRetrospective = => @.submitRetrospective()
        @scope.exportToExcel = => @.exportToExcel()
        @scope.setActiveTab = (tab) => @.setActiveTab(tab)
        @scope.isActiveTab = (tab) => @.isActiveTab(tab)
        @scope.setTeamMood = (mood) => @.setTeamMood(mood)
        @scope.isTeamMoodSelected = (mood) => @.isTeamMoodSelected(mood)
        @scope.addWentWell = => @.addWentWell()
        @scope.removeWentWell = (index) => @.removeWentWell(index)
        @scope.addToImprove = => @.addToImprove()
        @scope.removeToImprove = (index) => @.removeToImprove(index)
        @scope.addAction = => @.addAction()
        @scope.removeAction = (index) => @.removeAction(index)
        @scope.voteItem = (type, index) => @.voteItem(type, index)
        @scope.getVotes = (type, index) => @.getVotes(type, index)
        @scope.hasUserVoted = (type, index) => @.hasUserVoted(type, index)
        @scope.markActionCompleted = (action) => @.markActionCompleted(action)
        @scope.isActionCompleted = (action) => @.isActionCompleted(action)
        
        # Load initial data
        promise = @.loadInitialData()

        promise.then =>
            title = @translate.instant("SPRINT_RETROSPECTIVE.PAGE_TITLE", {projectName: @scope.project.name})
            description = @translate.instant("SPRINT_RETROSPECTIVE.PAGE_DESCRIPTION", {
                projectName: @scope.project.name
            })
            @appMetaService.setAll(title, description)

        promise.then null, @.onInitialDataError.bind(@)

    loadProject: ->
        project = @projectService.project.toJS()
        @scope.projectId = project.id
        @scope.project = project
        
        # Load users and roles
        @.fillUsersAndRoles(project.members, project.roles)
        @scope.activeUsers = angular.copy(@scope.users)
        
        # Get all sprints (closed and open)
        @scope.sprints = project.milestones || []
        
        # Select sprint from URL or most recent
        if @params.sprint
            @scope.selectedSprintId = parseInt(@params.sprint)
        else if @scope.sprints.length > 0
            sortedSprints = _.sortBy @scope.sprints, (s) -> 
                return -new Date(s.estimated_finish).getTime()
            @scope.selectedSprintId = sortedSprints[0].id
        
        @scope.$emit('project:loaded', project)
        return project

    loadMembers: ->
        user = @auth.getUser()
        @scope.user = user
        userId = parseInt(user?.id)
        
        console.log "Loading members for project:", @scope.project
        
        # Find current user in activeUsers
        @scope.currentUser = _.find @scope.activeUsers, (member) ->
            return parseInt(member.id) == userId
        
        # Get all team members for the dropdown
        @scope.teamMembers = _.map @scope.activeUsers, (member) ->
            return {
                id: member.id
                username: member.username || member.user?.username || 'Unknown'
                full_name: member.full_name || member.user?.full_name || member.full_name_display || ''
            }
        
        console.log "Team members loaded:", @scope.teamMembers
        
        # Get list of members without current user
        @scope.memberships = _.reject @scope.activeUsers, (member) ->
            return parseInt(member.id) == userId
        
        # Determine role
        if @scope.currentUser
            roleName = @scope.currentUser.role_name
            @scope.userRole = roleName
            
            if roleName
                roleNameLower = roleName.toLowerCase()
                @scope.isScrumMaster = roleNameLower.includes('scrum master') or roleNameLower == 'scrum-master'
                @scope.isDevelopmentTeam = not (roleNameLower.includes('product owner') or 
                                            roleNameLower.includes('scrum master') or 
                                            roleNameLower.includes('stakeholder'))
                @scope.isProductOwner = roleNameLower.includes('product owner') or roleNameLower == 'product-owner'
                @scope.isStakeholder = roleNameLower.includes('stakeholder')

    loadInitialData: ->
        project = @.loadProject()
        @.loadMembers()
        
        # Load retrospective if sprint selected
        if @scope.selectedSprintId
            return @.loadSprintRetrospective()
        else
            @scope.loading = false
            return @q.when()

    loadSprintRetrospective: ->
        return unless @scope.selectedSprintId
        
        @scope.loading = true
        @scope.error = null
        
        console.log "Loading retrospective for sprint:", @scope.selectedSprintId
        
        promise = @rs.sprintRetrospective.get(@scope.selectedSprintId)
        
        promise.then (response) =>
            console.log "Sprint Retrospective response:", response
            @scope.loading = false
            
            # Process sprint data
            @scope.sprintData = response.sprint
            @scope.retrospective = response.retrospective
            
            # Process team members
            if response.team_members and response.team_members.length > 0
                @scope.teamMembers = _.map response.team_members, (member) ->
                    return {
                        id: member.user__id || member.id
                        username: member.user__username || member.username || 'Unknown'
                        full_name: member.user__full_name || member.full_name || ''
                    }
            else if @scope.activeUsers and @scope.activeUsers.length > 0
                # Use activeUsers if team_members not provided
                @scope.teamMembers = _.map @scope.activeUsers, (member) ->
                    return {
                        id: member.id
                        username: member.username || member.user?.username || 'Unknown'
                        full_name: member.full_name || member.user?.full_name || member.full_name_display || ''
                    }
            else
                @scope.teamMembers = []
            
            console.log "Processed team members:", @scope.teamMembers
            
            @scope.previousActions = response.previous_actions || []
            @scope.isScrumMaster = response.is_scrum_master
            
            # Always initialize retrospectiveForm
            if @scope.retrospective
                @.loadExistingRetrospective()
            else
                # Initialize empty arrays
                @scope.retrospectiveForm = {
                    went_well: []
                    to_improve: []
                    action_items: []
                    team_mood: 'neutral'
                    previous_actions_completed: []
                }
            
            # Initialize voting state
            @.initializeVotingState()
            
            # Force scope update
            @scope.$apply() if !@scope.$$phase
            
        .catch (error) =>
            console.error "Error loading Sprint Retrospective:", error
            @scope.loading = false
            @scope.error = error.data?.error or @translate.instant("COMMON.ERROR")

    loadExistingRetrospective: ->
        retro = @scope.retrospective
        
        console.log "Loading existing retrospective:", retro
        
        @scope.retrospectiveForm = {
            went_well: retro.went_well || []
            to_improve: retro.to_improve || []
            action_items: retro.action_items || []
            team_mood: retro.team_mood || 'neutral'
            previous_actions_completed: retro.previous_actions_completed || []
        }
        
        console.log "Loaded retrospectiveForm:", @scope.retrospectiveForm
        
        # Load votes from the response
        for item, index in @scope.retrospectiveForm.went_well
            if item.votes
                @scope.voting["went_well_#{index}"] = item.votes
        
        for item, index in @scope.retrospectiveForm.to_improve
            if item.votes
                @scope.voting["to_improve_#{index}"] = item.votes

    initializeVotingState: ->
        # Check which items user has already voted on
        # This would come from backend in real implementation
        @scope.hasVoted = {}

    submitRetrospective: ->
        console.log "Submit retrospective called"
        console.log "Selected sprint ID:", @scope.selectedSprintId
        console.log "Is Scrum Master:", @scope.isScrumMaster
        console.log "Retrospective form:", @scope.retrospectiveForm
        
        return unless @scope.selectedSprintId
        
        # For now, allow anyone to submit if there's no retrospective yet
        if @scope.retrospective and not @scope.isScrumMaster
            @confirm.notify('error', null, @translate.instant('SPRINT_RETROSPECTIVE.ONLY_SM_CAN_SUBMIT'))
            return
        
        @scope.submitting = true
        
        # Clean up items (remove votes property before sending)
        cleanedWentWell = _.map @scope.retrospectiveForm.went_well, (item) ->
            return {
                text: item.text
                author_id: item.author_id
            }
        
        cleanedToImprove = _.map @scope.retrospectiveForm.to_improve, (item) ->
            return {
                text: item.text
                author_id: item.author_id
            }
        
        # Prepare data
        data = {
            sprint_id: @scope.selectedSprintId
            went_well: cleanedWentWell
            to_improve: cleanedToImprove
            action_items: @scope.retrospectiveForm.action_items
            team_mood: @scope.retrospectiveForm.team_mood
            previous_actions_completed: @scope.retrospectiveForm.previous_actions_completed
        }
        
        console.log "Submitting retrospective data:", data
        
        promise = @rs.sprintRetrospective.create(data)
        
        promise.then (response) =>
            console.log "Retrospective submitted successfully:", response
            @scope.submitting = false
            @confirm.notify('success', null, @translate.instant('SPRINT_RETROSPECTIVE.SUBMITTED'))
            
            # Reload data
            @.loadSprintRetrospective()
            
        .catch (error) =>
            console.error "Error submitting retrospective:", error
            @scope.submitting = false
            errorMsg = error.data?.error or error.data?.detail or @translate.instant("COMMON.ERROR")
            @confirm.notify('error', null, errorMsg)

    setActiveTab: (tab) ->
        console.log "Setting active tab to:", tab
        @scope.activeTab = tab

    isActiveTab: (tab) ->
        result = @scope.activeTab == tab
        console.log "Checking if", tab, "is active. Current active:", @scope.activeTab, "Result:", result
        return result

    setTeamMood: (mood) ->
        @scope.retrospectiveForm.team_mood = mood

    isTeamMoodSelected: (mood) ->
        return @scope.retrospectiveForm.team_mood == mood

    addWentWell: ->
        console.log "=== addWentWell called ==="
        
        # Usar el modelo de Angular correctamente
        textValue = @scope.forms.newWentWell
        
        console.log "Input value:", textValue
        
        return unless textValue?.trim()
        
        newItem = {
            text: textValue.trim()
            author_id: @scope.currentUser?.id
            votes: 0
        }
        
        console.log "Item to add:", newItem
        
        @scope.retrospectiveForm.went_well.push(newItem)
        
        # Limpiar el modelo
        @scope.forms.newWentWell = ''
        
        console.log "Went well items after adding:", @scope.retrospectiveForm.went_well

    removeWentWell: (index) ->
        @scope.retrospectiveForm.went_well.splice(index, 1)

    addToImprove: ->
        console.log "=== addToImprove called ==="
        
        # Usar el modelo de Angular correctamente
        textValue = @scope.forms.newToImprove
        
        console.log "Input value:", textValue
        
        return unless textValue?.trim()
        
        newItem = {
            text: textValue.trim()
            author_id: @scope.currentUser?.id
            votes: 0
        }
        
        console.log "Item to add:", newItem
        
        @scope.retrospectiveForm.to_improve.push(newItem)
        
        # Limpiar el modelo
        @scope.forms.newToImprove = ''
        
        console.log "To improve items after adding:", @scope.retrospectiveForm.to_improve

    removeToImprove: (index) ->
        @scope.retrospectiveForm.to_improve.splice(index, 1)

    addAction: ->
        console.log "=== addAction called ==="
        
        # Usar el modelo de Angular correctamente
        actionText = @scope.forms.newAction.action
        responsibleId = @scope.forms.newAction.responsible_id
        dueDate = @scope.forms.newAction.due_date
        
        return unless actionText?.trim()
        
        actionItem = {
            action: actionText.trim()
            responsible_id: responsibleId || null
            due_date: dueDate || null
            completed: false
        }
        
        console.log "Action item to add:", actionItem
        
        @scope.retrospectiveForm.action_items.push(actionItem)
        
        # Limpiar formulario
        @scope.forms.newAction = {
            action: ''
            responsible_id: null
            due_date: null
        }
        
        console.log "Action items after adding:", @scope.retrospectiveForm.action_items
        
        # Limpiar formulario
        actionInput.value = ''
        if responsibleSelect
            responsibleSelect.value = ''
        if dueDateInput
            dueDateInput.value = ''
        
        # Forzar actualización de Angular
        @scope.$apply() if !@scope.$phase
        
        console.log "Action items after adding:", @scope.retrospectiveForm.action_items

    removeAction: (index) ->
        @scope.retrospectiveForm.action_items.splice(index, 1)

    voteItem: (type, index) ->
        # Check if user already voted
        voteKey = "#{type}_#{index}"
        if @scope.hasVoted[voteKey]
            @confirm.notify('warning', null, @translate.instant('SPRINT_RETROSPECTIVE.ALREADY_VOTED'))
            return
        
        # Send vote to backend
        data = {
            sprint_id: @scope.selectedSprintId
            item_type: type
            item_index: index
        }
        
        promise = @rs.retrospectiveVote.create(data)
        
        promise.then (response) =>
            # Update vote count
            @scope.voting[voteKey] = response.votes
            @scope.hasVoted[voteKey] = true
            
            # Update item votes
            if type == 'went_well'
                @scope.retrospectiveForm.went_well[index].votes = response.votes
            else if type == 'to_improve'
                @scope.retrospectiveForm.to_improve[index].votes = response.votes
            
        .catch (error) =>
            console.error "Error voting:", error
            errorMsg = error.data?.error or @translate.instant("COMMON.ERROR")
            @confirm.notify('error', null, errorMsg)

    getVotes: (type, index) ->
        voteKey = "#{type}_#{index}"
        return @scope.voting[voteKey] || 0

    hasUserVoted: (type, index) ->
        voteKey = "#{type}_#{index}"
        return @scope.hasVoted[voteKey] || false

    markActionCompleted: (action) ->
        # Find if this action is in previous actions completed
        actionId = "#{action.action}_#{action.responsible_id}"
        
        idx = @scope.retrospectiveForm.previous_actions_completed.indexOf(actionId)
        
        if idx >= 0
            # Remove from completed
            @scope.retrospectiveForm.previous_actions_completed.splice(idx, 1)
        else
            # Add to completed
            @scope.retrospectiveForm.previous_actions_completed.push(actionId)

    isActionCompleted: (action) ->
        actionId = "#{action.action}_#{action.responsible_id}"
        return @scope.retrospectiveForm.previous_actions_completed.indexOf(actionId) >= 0

    exportToExcel: ->
        return unless @scope.selectedSprintId
        
        console.log "Export clicked - Sprint ID:", @scope.selectedSprintId
        
        # Notify start
        try
            @confirm.notify('info', null, @translate.instant('SPRINT_RETROSPECTIVE.GENERATING_EXCEL'))
        catch e
            console.log "Notification not available"
        
        # Build URL
        baseUrl = "/api/v1/sprint-retrospective/export/"
        
        # Get auth token
        token = @auth.getToken()
        
        # Fetch with authentication
        fetchUrl = "#{baseUrl}?sprint_id=#{@scope.selectedSprintId}"
        
        fetch(fetchUrl, {
            method: 'GET',
            headers: {
                'Authorization': "Bearer #{token}"
                'X-Session-Token': token
            },
            credentials: 'include'
        })
        .then (response) =>
            if not response.ok
                throw new Error("Error downloading: #{response.status}")
            return response.blob()
        .then (blob) =>
            # Create download link
            url = window.URL.createObjectURL(blob)
            link = document.createElement('a')
            link.href = url
            sprintName = @scope.sprintData?.name or @scope.selectedSprintId
            link.download = "sprint_retrospective_#{sprintName}.xlsx"
            
            # Trigger download
            document.body.appendChild(link)
            link.click()
            
            # Cleanup
            setTimeout ->
                document.body.removeChild(link)
                window.URL.revokeObjectURL(url)
            , 100
            
            # Notify success
            try
                @confirm.notify('success', null, @translate.instant('SPRINT_RETROSPECTIVE.DOWNLOAD_COMPLETE'))
            catch e
                console.log "Notification not available"
                
        .catch (error) =>
            console.error "Error exporting:", error
            try
                @confirm.notify('error', null, @translate.instant('SPRINT_RETROSPECTIVE.EXPORT_ERROR'))
            catch e
                console.log "Notification not available"

module.controller("SprintRetrospectiveController", SprintRetrospectiveController)


#############################################################################
## Sprint Retrospective Menu Directive
#############################################################################

SprintRetrospectiveMenuDirective = ($translate) ->
    return {
        template: """
        <div class="sprint-retrospective-menu">
            <h3>{{ 'SPRINT_RETROSPECTIVE.MENU_TITLE' | translate }}</h3>
            
            <div class="menu-section" ng-if="selectedSprintId && sprintData">
                <h4>{{ 'SPRINT_RETROSPECTIVE.SPRINT_INFO' | translate }}</h4>
                <div class="stats-list">
                    <div class="stat">
                        <span class="label">{{ 'SPRINT_RETROSPECTIVE.SPRINT' | translate }}:</span>
                        <span class="value">{{ sprintData.name }}</span>
                    </div>
                    <div class="stat" ng-if="retrospective">
                        <span class="label">{{ 'SPRINT_RETROSPECTIVE.TEAM_MOOD' | translate }}:</span>
                        <span class="value">
                            <span class="mood-emoji">
                                {{ retrospective.team_mood == 'terrible' ? '😞' : 
                                   retrospective.team_mood == 'bad' ? '😕' : 
                                   retrospective.team_mood == 'neutral' ? '😐' : 
                                   retrospective.team_mood == 'good' ? '🙂' : '😊' }}
                            </span>
                            {{ retrospective.team_mood_display }}
                        </span>
                    </div>
                    <div class="stat" ng-if="retrospective && retrospective.velocity_achieved">
                        <span class="label">{{ 'SPRINT_RETROSPECTIVE.VELOCITY' | translate }}:</span>
                        <span class="value">{{ retrospective.velocity_achieved }}</span>
                    </div>
                    <div class="stat" ng-if="retrospective && retrospective.commitment_accuracy">
                        <span class="label">{{ 'SPRINT_RETROSPECTIVE.ACCURACY' | translate }}:</span>
                        <span class="value">{{ retrospective.completion_percentage }}</span>
                    </div>
                </div>
            </div>
            
            <div class="menu-section" ng-if="retrospective">
                <h4>{{ 'SPRINT_RETROSPECTIVE.ACTIONS_SUMMARY' | translate }}</h4>
                <p class="status-info">
                    <tg-svg svg-icon="icon-task"></tg-svg>
                    {{ retrospective.action_items.length }} {{ 'SPRINT_RETROSPECTIVE.ACTIONS_DEFINED' | translate }}
                </p>
            </div>
            
            <div class="menu-section" ng-if="previousActions && previousActions.length > 0">
                <h4>{{ 'SPRINT_RETROSPECTIVE.PREVIOUS_ACTIONS' | translate }}</h4>
                <p class="status-info">
                    <tg-svg svg-icon="icon-history"></tg-svg>
                    {{ previousActions.length }} {{ 'SPRINT_RETROSPECTIVE.FROM_PREVIOUS_SPRINTS' | translate }}
                </p>
            </div>
        </div>
        """
        scope: false
    }

module.directive("tgSprintRetrospectiveMenu", ["$translate", SprintRetrospectiveMenuDirective])