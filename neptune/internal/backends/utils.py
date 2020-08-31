#
# Copyright (c) 2020, Neptune Labs Sp. z o.o.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import logging
import socket
import sys
import time
from typing import Optional, Dict

from urllib.parse import urlparse

import click
import requests

from bravado.client import SwaggerClient
from bravado.exception import BravadoConnectionError, BravadoTimeoutError, HTTPForbidden, \
    HTTPInternalServerError, HTTPServerError, HTTPUnauthorized, HTTPServiceUnavailable, HTTPRequestTimeout, \
    HTTPGatewayTimeout, HTTPBadGateway, HTTPClientError
from bravado.http_client import HttpClient
from bravado_core.formatter import SwaggerFormat
from packaging.version import Version
from requests import Session

from neptune.exceptions import SSLError, ConnectionLost, InternalServerError, Unauthorized, Forbidden, \
    CannotResolveHostname, UnsupportedClientVersion, BadUsage
from neptune.internal.backends.api_model import ClientConfig
from neptune.internal.utils import replace_patch_version

_logger = logging.getLogger(__name__)


def with_api_exceptions_handler(func):

    def wrapper(*args, **kwargs):
        for retry in range(0, 3):
            try:
                return func(*args, **kwargs)
            except requests.exceptions.SSLError as e:
                raise SSLError() from e
            except (BravadoConnectionError, BravadoTimeoutError,
                    requests.exceptions.ConnectionError, requests.exceptions.Timeout,
                    HTTPRequestTimeout, HTTPServiceUnavailable, HTTPGatewayTimeout, HTTPBadGateway):
                time.sleep(2 ** retry)
                continue
            except HTTPServerError as e:
                raise InternalServerError() from e
            except HTTPUnauthorized:
                raise Unauthorized()
            except HTTPForbidden:
                raise Forbidden()
            except HTTPClientError as e:
                raise BadUsage("API status code {}".format(e.status_code)) from e
            except requests.exceptions.RequestException as e:
                if e.response is None:
                    raise
                status_code = e.response.status_code
                if status_code in (
                        HTTPRequestTimeout.status_code,
                        HTTPBadGateway.status_code,
                        HTTPServiceUnavailable.status_code,
                        HTTPGatewayTimeout.status_code):
                    time.sleep(2 ** retry)
                    continue
                elif status_code >= HTTPInternalServerError.status_code:
                    raise InternalServerError() from e
                elif status_code == HTTPUnauthorized.status_code:
                    raise Unauthorized()
                elif status_code == HTTPForbidden.status_code:
                    raise Forbidden()
                elif 400 <= status_code < 500:
                    raise BadUsage("API status code {}".format(status_code)) from e
                else:
                    raise
        raise ConnectionLost()

    return wrapper


def verify_host_resolution(url: str) -> None:
    host = urlparse(url).netloc.split(':')[0]
    try:
        socket.gethostbyname(host)
    except socket.gaierror:
        raise CannotResolveHostname(host)


uuid_format = SwaggerFormat(
    format='uuid',
    to_python=lambda x: x,
    to_wire=lambda x: x,
    validate=lambda x: None, description='')


@with_api_exceptions_handler
def create_swagger_client(url: str, http_client: HttpClient) -> SwaggerClient:
    return SwaggerClient.from_url(
        url,
        config=dict(
            validate_swagger_spec=False,
            validate_requests=False,
            validate_responses=False,
            formats=[uuid_format]
        ),
        http_client=http_client)


def verify_client_version(client_config: ClientConfig, version: Version):
    version_with_patch_0 = Version(replace_patch_version(str(version)))
    if client_config.min_compatible_version and client_config.min_compatible_version > version:
        raise UnsupportedClientVersion(version, min_version=client_config.min_compatible_version)
    if client_config.max_compatible_version and client_config.max_compatible_version < version_with_patch_0:
        raise UnsupportedClientVersion(version, max_version=client_config.max_compatible_version)
    if client_config.min_recommended_version and client_config.min_recommended_version > version:
        click.echo(
            "WARNING: There is a new version of neptune-client {} (installed: {}).".format(
                client_config.min_recommended_version, version),
            sys.stderr)


def update_session_proxies(session: Session, proxies: Optional[Dict[str, str]]):
    if proxies:
        try:
            session.proxies.update(proxies)
        except (TypeError, ValueError):
            raise ValueError("Wrong proxies format: {}".format(proxies))
