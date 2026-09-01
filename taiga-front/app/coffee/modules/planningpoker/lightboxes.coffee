# ###
# # Planning Poker - Crear sesión (guardar formulario)
# ###

# taiga = @.taiga
# debounce = @.taiga.debounce

# module = angular.module("taigaPlanningPoker")

# CreatePlanningSessionDirective = ($repo, $confirm, $loading, lightboxService, $model) ->
#     link = ($scope, $el, attrs) ->
#         submit = debounce 2000, (event) ->
#             event.preventDefault()

#             form = $el.find("form").checksley()
#             if not form.validate()
#                 return

#             currentLoading = $loading().target($el.find("button[type='submit']")).start()
#             if currentLoading.isLoading()
#                 return

#             # Si ya tienes los IDs seleccionados desde el scope
#             data = {
#                 name: $scope.obj.name
#                 description: $scope.obj.description
#                 project: $scope.obj.project
#                 user_stories: $scope.obj.user_stories
#             }

#             $repo.create("planning-sessions", data).then (result) ->
#                 currentLoading.finish()
#                 $confirm.notify("success")
#                 lightboxService.close($el)

#             , (error) ->
#                 currentLoading.finish()
#                 form.setErrors(error)
#                 $confirm.notify("error")

#         $el.on "submit", "form", submit

#         $scope.$on "$destroy", -> $el.off()

#     return {link: link}

# module.directive("tgLbCreatePlanningSession", [
#     "$tgRepo", "$tgConfirm", "$tgLoading", "lightboxService", "$tgModel", CreatePlanningSessionDirective
# ])
