# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos INC

from django import http
from django.conf import settings


CORS_ALLOWED_ORIGINS = "*"
CORS_ALLOWED_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]
CORS_ALLOWED_HEADERS = ["content-type", "x-requested-with",
                        "authorization", "accept-encoding",
                        "x-disable-pagination", "x-lazy-pagination",
                        "x-host", "x-session-id", "set-orders"]
CORS_ALLOWED_CREDENTIALS = True
CORS_EXPOSE_HEADERS = ["x-pagination-count", "x-paginated", "x-paginated-by",
                       "x-pagination-current", "x-pagination-next", "x-pagination-prev",
                       "x-site-host", "x-site-register"]

CORS_EXTRA_EXPOSE_HEADERS = getattr(settings, "APP_EXTRA_EXPOSE_HEADERS", [])


class CorsMiddleware(object):
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Manejar peticiones OPTIONS (preflight)
        if request.method == "OPTIONS":
            response = http.HttpResponse()
            self._populate_response(response)
            return response
        
        # Para otras peticiones, continuar normalmente
        response = self.get_response(request)
        self._populate_response(response)
        return response

    def _populate_response(self, response):
        response["Access-Control-Allow-Origin"] = CORS_ALLOWED_ORIGINS
        response["Access-Control-Allow-Methods"] = ",".join(CORS_ALLOWED_METHODS)
        response["Access-Control-Allow-Headers"] = ",".join(CORS_ALLOWED_HEADERS)
        response["Access-Control-Expose-Headers"] = ",".join(CORS_EXPOSE_HEADERS + CORS_EXTRA_EXPOSE_HEADERS)
        response["Access-Control-Max-Age"] = "1800"

        if CORS_ALLOWED_CREDENTIALS:
            response["Access-Control-Allow-Credentials"] = "true"

    def process_request(self, request):
        # Este método ya no es necesario con el nuevo enfoque
        return None

    def process_response(self, request, response):
        # Este método ya no es necesario con el nuevo enfoque
        return response