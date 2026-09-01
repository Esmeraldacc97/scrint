taiga = @.taiga

resourceProvider = ($repo, $http, $tgUrls) ->
    service = {}

    service.planningSessions = {
        list: (projectId) ->
            return $repo.queryMany("planning-sessions", {project: projectId})

        create: (data) ->
            # Asegurar que name tenga el valor de subject si viene del lightbox
            if data.subject and not data.name
                data.name = data.subject
            else if data.name and not data.subject
                data.subject = data.name
            
            console.log("📤 Creando sesión con datos mapeados:", data)
            return $repo.create("planning-sessions", data)

        get: (id) ->
            return $repo.queryOne("planning-sessions", id)
    }

    service.participants = {
        list: (filters) ->
            return $repo.queryMany("participants", filters)

        get: (id) ->
            return $repo.queryOne("participants", id)
    }

    service.estimations = {
        list: (filters) ->
            console.log("🔍 Listando estimaciones con filtros:", filters)
            return $repo.queryMany("estimations", filters)

        create: (data) ->
            console.log("📤 Creando estimación con datos:", data)
            # Usar la URL completa para estimaciones
            url = $tgUrls.resolve("estimations")
            return $http.post(url, data).then (response) -> 
                console.log("✅ Respuesta de creación de estimación:", response.data)
                return response.data

        update: (id, data) ->
            return $repo.save("estimations", id, data)
    }

    # Agregar servicio http para acceso directo
    service.http = $http

    return (instance) ->
        console.log("🚀 Registrando servicios de Planning Poker en la instancia")
        instance.planningSessions = service.planningSessions
        instance.participants = service.participants
        instance.estimations = service.estimations
        instance.http = service.http
        console.log("✅ Servicios registrados:", Object.keys(instance))

module = angular.module("taigaResources")
module.factory("$tgPlanningPokerResourcesProvider", ["$tgRepo", "$tgHttp", "$tgUrls", resourceProvider])