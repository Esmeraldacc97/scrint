# app/coffee/modules/resources/dailyscrum.coffee

taiga = @.taiga

resourceProvider = ($repo, $http, $tgUrls) ->
    service = {}

    service.dailyMeetings = {
        list: (params) ->
            return $repo.queryMany("daily-meetings", params)

        getDailyMeetingToday: (projectId) ->
            url = $tgUrls.resolve("daily-meeting-today")
            
            # Construir la URL con el parámetro directamente
            urlWithParams = "#{url}?project=#{projectId}"
            
            console.log "URL final:", urlWithParams
            
            # Hacer la petición sin el objeto params
            return $http.get(urlWithParams).then (response) ->
                return response.data

        get: (meetingId) ->
            return $repo.queryOne("daily-meetings", meetingId)

        create: (data) ->
            return $repo.create("daily-meetings", data)

        createResponse: (meetingId, data) ->
            url = $tgUrls.resolve("daily-meeting-response", meetingId)
            return $http.post(url, data).then (response) ->
                return response.data

        getMyResponse: (meetingId) ->
            url = $tgUrls.resolve("daily-meeting-my-response", meetingId)
            return $http.get(url).then (response) ->
                return response.data

        getExportUrl: (meetingId) ->
            url = $tgUrls.resolve("daily-meeting-export", meetingId)
            console.log "Export URL generada:", url
            return url
    }

    return (instance) ->
        instance.dailyMeetings = service.dailyMeetings

module = angular.module("taigaResources")
module.factory("$tgDailyScrumResourcesProvider", ["$tgRepo", "$tgHttp", "$tgUrls", resourceProvider])