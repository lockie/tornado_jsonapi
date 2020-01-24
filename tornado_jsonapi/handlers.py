#!/usr/bin/env python3
# vim: set fileencoding=utf8 :

import collections
import traceback
import json
import python_jsonschema_objects as pjs
import status
import accept
import tornado
import tornado.web
from tornado.log import app_log, gen_log
from tornado.concurrent import is_future

from . import __version__, _schemas
from .exceptions import APIError


class APIHandler(tornado.web.RequestHandler):
    """
    Basic :py:class:`tornado.web.RequestHandler` for JSON API.
    It handles validating both input and output documents, rendering resources
    to JSON, error processing and other aspects of JSON API.
    Subclass it to add extra functionality, e.g. authorization or `JSON API
    extension support <http://jsonapi.org/extensions/>`_.
    """

    def initialize(self, resource):
        self._resource = resource

    def _get_meta(self):
        return {
            "meta": {"tornado_jsonapi_version": __version__},
            "jsonapi": {"version": "1.0"},
        }

    def _get_content_type(self):
        return "application/vnd.api+json"

    def set_default_headers(self):
        self.set_header("Content-Type", self._get_content_type())
        self.set_header(
            "Server",
            "TornadoServer/{} tornado_jsonapi/{}".format(
                tornado.version, __version__
            ),
        )

    def write_error(self, status_code, **kwargs):
        exc_info = kwargs["exc_info"] if "exc_info" in kwargs else None
        exception = exc_info[1] if exc_info else None
        reason = ""
        if isinstance(exception, tornado.web.HTTPError):
            reason = exception.reason
        if not reason:
            reason = tornado.httputil.responses.get(
                status_code, "Unknown error"
            )
        detail = ""
        if isinstance(exception, tornado.web.HTTPError):
            detail = (
                exception.log_message % exception.args
                if exception.log_message
                else reason
            )
        if self.settings.get("serve_traceback") and exc_info:
            # in debug mode, try to send a traceback
            for line in traceback.format_exception(*exc_info):
                detail += "\r\n" + line
        error_id = (
            exception.error_id
            if hasattr(exception, "error_id")
            else APIError._generate_id()
        )
        self.finish(
            json.dumps(
                dict(
                    errors=[
                        {
                            "id": error_id,
                            "status": str(status_code),
                            "title": reason,
                            "detail": detail,
                        }
                    ],
                    **self._get_meta()
                ),
                ensure_ascii=False,
                indent=4,
            )
        )

    def log_exception(self, typ, value, tb):
        if isinstance(value, APIError):
            app_log.error(
                "API error %s: %s\n%r",
                value.error_id,
                value.log_message % value.args if value.log_message else "",
                self.request,
                exc_info=(typ, value, tb),
            )
        elif isinstance(value, tornado.web.HTTPError):
            if value.log_message:
                format = "%d %s: " + value.log_message
                args = [value.status_code, self._request_summary()] + list(
                    value.args
                )
                gen_log.warning(format, *args)
        else:
            value.error_id = APIError._generate_id()
            app_log.error(
                "Uncaught exception %s %s\n%r",
                self._request_summary(),
                value.error_id,
                self.request,
                exc_info=(typ, value, tb),
            )

    def acceptable(self, extensions):
        """
        Return whether server supports given extensions. By default do not
        support any extensions.

        :param dict sender: dictionary of Accept header parameters, e.g.
            :code:`{'supported-ext': 'bulk,jsonpatch'}`
        """
        return not extensions

    def prepare(self):
        if len(self.request.body) != 0:
            mt = accept.parse(self.request.headers.get("Content-Type"))[0]
            if mt.media_type != self._get_content_type() or not self.acceptable(
                mt.params
            ):
                raise APIError(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "")
        accept_header = self.request.headers.get("Accept")
        if not accept_header:
            return  # allow missing Accept header
        for a in accept.parse(accept_header):
            if (
                a.all_types or
                a.media_type.split("/")[0] == "application" and
                a.all_subtypes
            ):
                return
            if a.media_type == self._get_content_type():
                if self.acceptable(a.params):
                    return
        raise APIError(status.HTTP_406_NOT_ACCEPTABLE, "")

    def render_resource(self, resource, nullable=True):
        """
        Utility function
        """
        if resource is None:
            if nullable:
                return None
            else:
                raise APIError(status.HTTP_404_NOT_FOUND, "")
        resource_attributes = resource.attributes()
        attributes = self._resource._schema()
        blacklist_attr = []
        for attr_name in attributes.keys():
            if attr_name in resource_attributes:
                attributes[attr_name] = resource_attributes[attr_name]
            else:
                blacklist_attr.append(attr_name)

        for attr in blacklist_attr:
            attributes.pop(attr, None)
        attributes.validate()

        return {
            "id": resource.id_(),
            "type": resource.type_(),
            "attributes": attributes._properties,
        }

    def render(self, resources, nullable=True, additional=None):
        data = {}
        json_resources = []
        if isinstance(resources, collections.Sequence):
            for resource in resources:
                json_resources.append(self.render_resource(resource))
            data.update({"data_len": len(resources)})
        else:
            json_resources = self.render_resource(resources, nullable)

        if additional:
            data.update(additional)
        data.update(dict(data=json_resources, **self._get_meta()))

        self.finish(json.dumps(data, ensure_ascii=False, indent=4))

    def _get_request_data(self, schema):
        """
        Get and validate request JSON data according to given schema
        """
        try:
            d = json.loads(self.request.body.decode(encoding="UTF-8"))
        except ValueError as err:
            raise APIError(status.HTTP_400_BAD_REQUEST, str(err)) from err
        try:
            data = schema(**d)
            data.validate()
        except pjs.validators.ValidationError as err:
            raise APIError(status.HTTP_400_BAD_REQUEST, str(err)) from err
        return data["data"]

    def _get_resource(self, data, validate=True):
        if data.get("type") != self._resource.name():
            raise APIError(
                status.HTTP_409_CONFLICT,
                'Expecting object of type "%s"',
                self._resource.name(),
            )
        if data["attributes"] is None:
            raise APIError(
                status.HTTP_400_BAD_REQUEST, "Missing object attributes"
            )
        attributes = data["attributes"].as_dict()
        if validate:
            try:
                attrs = self._resource._schema(**attributes)
                attrs.validate()
            except pjs.validators.ValidationError as err:
                raise APIError(status.HTTP_400_BAD_REQUEST, str(err)) from err
        return attributes

    @tornado.gen.coroutine
    def get(self, id_=None):
        """
        GET method, see
        `spec <http://jsonapi.org/format/1.0/#fetching-resources>`__.
        Decorate with :py:func:`tornado.gen.coroutine` when subclassing.
        """

        limit = (
            int(self.request.arguments["limit"][0])
            if "limit" in self.request.arguments
            else 0
        )
        server_limit = (
            self.settings["jsonapi_limit"]
            if "jsonapi_limit" in self.settings
            else 0
        )
        if server_limit > 0 and (limit > server_limit or limit == 0):
            limit = server_limit

        page = (
            int(self.request.arguments["page"][0])
            if "page" in self.request.arguments
            else 0
        )

        if not id_:
            res = self._resource.list_(limit=limit, page=page)
            while is_future(res):
                res = yield res
            count = self._resource.list_count()
            while is_future(count):
                count = yield count

            self.render(
                res,
                additional={
                    "limits": {"total": count, "limit": limit, "page": page}
                },
            )
        else:
            res = self._resource.read(id_)
            while is_future(res):
                res = yield res
            self.render(res)

    @tornado.gen.coroutine
    def post(self, id_=None):
        """
        POST method, see
        `spec <http://jsonapi.org/format/1.0/#crud-creating>`__.
        Decorate with :py:func:`tornado.gen.coroutine` when subclassing.
        """
        if id_:
            raise APIError(status.HTTP_400_BAD_REQUEST, "Extra id in request")
        data = self._get_request_data(_schemas.postDataSchema())
        if data["id"] is not None:
            raise APIError(
                status.HTTP_403_FORBIDDEN,
                "Client-generated resource ID is not supported",
            )
        resource = self._resource.create(self._get_resource(data))
        while is_future(resource):
            resource = yield resource
        if not resource:
            raise APIError()
        self.set_status(status.HTTP_201_CREATED)
        self.set_header("Location", self.request.uri + resource.id_())
        self.render(resource)

    @tornado.gen.coroutine
    def patch(self, id_):
        """
        PATCH method, see
        `spec <http://jsonapi.org/format/1.0/#crud-updating>`__.
        Decorate with :py:func:`tornado.gen.coroutine` when subclassing.
        """
        if not id_:
            raise APIError(status.HTTP_400_BAD_REQUEST, "Missing ID")
        data = self._get_request_data(_schemas.patchDataSchema())
        if data["id"] != id_:
            raise APIError(status.HTTP_400_BAD_REQUEST, "ID mismatch")
        exists = self._resource.exists(id_)
        while is_future(exists):
            exists = yield exists
        if not exists:
            raise APIError(status.HTTP_404_NOT_FOUND, "No such resource")
        res = self._get_resource(data, validate=False)
        resource = self._resource.update(id_, res)
        while is_future(resource):
            resource = yield resource
        if not resource:
            raise APIError()
        self.render(resource)

    @tornado.gen.coroutine
    def delete(self, id_):
        """
        DELETE method, see
        `spec <http://jsonapi.org/format/1.0/#crud-deleting>`__.
        Decorate with :py:func:`tornado.gen.coroutine` when subclassing.
        """
        if not id_:
            raise APIError(status.HTTP_400_BAD_REQUEST, "Missing ID")
        exists = self._resource.exists(id_)
        while is_future(exists):
            exists = yield exists
        if not exists:
            raise APIError(status.HTTP_404_NOT_FOUND, "No such resource")
        res = self._resource.delete(id_)
        while is_future(res):
            res = yield res
        if not res:
            raise APIError()
        self.set_status(status.HTTP_204_NO_CONTENT)
        self.clear_header("Content-Type")

    def on_finish(self):
        if hasattr(self._resource, "_on_request_end"):
            self._resource._on_request_end()


class NotFoundErrorAPIHandler(APIHandler):
    """
    Handler for 404 error providing correct API
    `response <http://jsonapi.org/format/1.0/#error-objects>`_. Do not use it
    directly, use :py:func:`not_found_handling_settings` instead.
    """

    def prepare(self):
        super().prepare()
        raise APIError(status.HTTP_404_NOT_FOUND, "Resource not found")


def not_found_handling_settings():
    """
    Settings dict for :py:class:`tornado.web.Application` to use
    :py:class:`NotFoundErrorAPIHandler` as default 404 error handler. Use this
    as follows:

    .. code-block:: python
        :emphasize-lines: 5

        application = tornado.web.Application([
            (
                # ... handlers ...
            ),
        ], **tornado_jsonapi.handlers.not_found_handling_settings())
        application.listen()
    """
    return {
        "default_handler_class": NotFoundErrorAPIHandler,
        "default_handler_args": dict(resource={}),
    }
