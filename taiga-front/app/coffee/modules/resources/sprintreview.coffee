# app/coffee/modules/resources/sprintreview.coffee

taiga = @.taiga

resourceProvider = ($repo, $http, $tgUrls) ->
    service = {}

    service.sprintReview = {
        get: (sprintId) ->
            url = $tgUrls.resolve("sprint-review")
            urlWithParams = "#{url}?sprint_id=#{sprintId}"
            
            return $http.get(urlWithParams).then (response) ->
                return response.data

        list: (sprintId) ->
            # Para obtener todos los feedbacks de un sprint
            # Por ahora usar el mismo endpoint con un parámetro adicional
            url = $tgUrls.resolve("sprint-review")
            urlWithParams = "#{url}?sprint_id=#{sprintId}&list_all=true"
            
            return $http.get(urlWithParams).then (response) ->
                # Si el backend devuelve una lista, usarla
                # Si no, crear una lista con el feedback actual
                if response.data and Array.isArray(response.data)
                    return response.data
                else if response.data and response.data.all_feedbacks
                    return response.data.all_feedbacks
                else
                    return []

        create: (data) ->
            url = $tgUrls.resolve("sprint-review")
            return $http.post(url, data).then (response) ->
                return response.data

        update: (sprintId, data) ->
            # Actualizar es lo mismo que crear con el mismo sprint_id
            return service.sprintReview.create(data)

        getExportUrl: (sprintId) ->
            url = $tgUrls.resolve("sprint-review-export")
            return "#{url}?sprint_id=#{sprintId}"
    }

    return (instance) ->
        instance.sprintReview = service.sprintReview

module = angular.module("taigaResources")
module.factory("$tgSprintReviewResourcesProvider", ["$tgRepo", "$tgHttp", "$tgUrls", resourceProvider])