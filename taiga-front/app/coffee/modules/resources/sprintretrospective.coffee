# app/coffee/modules/resources/sprintretrospective.coffee

taiga = @.taiga

resourceProvider = ($repo, $http, $tgUrls) ->
    service = {}

    service.sprintRetrospective = {
        get: (sprintId) ->
            url = $tgUrls.resolve("sprint-retrospective")
            urlWithParams = "#{url}?sprint_id=#{sprintId}"
            
            console.log "Fetching retrospective from:", urlWithParams
            
            return $http.get(urlWithParams).then (response) ->
                console.log "Retrospective API response:", response.data
                return response.data

        create: (data) ->
            url = $tgUrls.resolve("sprint-retrospective")
            console.log "Creating/updating retrospective with data:", data
            return $http.post(url, data).then (response) ->
                return response.data

        update: (sprintId, data) ->
            # Update is same as create with same sprint_id
            return service.sprintRetrospective.create(data)

        getExportUrl: (sprintId) ->
            url = $tgUrls.resolve("sprint-retrospective-export")
            return "#{url}?sprint_id=#{sprintId}"
    }

    service.retrospectiveVote = {
        create: (data) ->
            url = $tgUrls.resolve("retrospective-vote")
            return $http.post(url, data).then (response) ->
                return response.data

        get: (sprintId, itemType, itemIndex) ->
            url = $tgUrls.resolve("retrospective-vote")
            urlWithParams = "#{url}?sprint_id=#{sprintId}&item_type=#{itemType}&item_index=#{itemIndex}"
            
            return $http.get(urlWithParams).then (response) ->
                return response.data
    }

    return (instance) ->
        instance.sprintRetrospective = service.sprintRetrospective
        instance.retrospectiveVote = service.retrospectiveVote

module = angular.module("taigaResources")
module.factory("$tgSprintRetrospectiveResourcesProvider", ["$tgRepo", "$tgHttp", "$tgUrls", resourceProvider])