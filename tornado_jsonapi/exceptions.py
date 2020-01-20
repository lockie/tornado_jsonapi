#!/usr/bin/env python3
# vim: set fileencoding=utf8 :

import datetime
import hashlib
import status
import tornado.web


class APIError(tornado.web.HTTPError):
    """
    Basic API error for using in client code.
    Each :py:class:`APIError` is assigned an unique error ID, which is both
    written to log and returned to API client (as ``id`` field of ``error``
    object) to simplify debugging.

    Usage example:

    .. code-block:: python

        class MyResource(tornado_jsonapi.resource.Base):
            def read(self, id_):
                if not self.ham():
                    raise tornado_jsonapi.exceptions.APIError(details=\
'No ham left!')

    :param int status_code: HTTP status code
    :param str details: Details of the error to be shown to API client and
        written to log. May contain ``%s``-style placeholders, which will be
        filled in with remaining positional parameters.
    """

    def __init__(
        self,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        details="Unspecified API error",
        *args,
        **kwargs
    ):
        super().__init__(status_code, details, *args, **kwargs)
        self.error_id = APIError._generate_id()

    @staticmethod
    def _generate_id():
        now = str(datetime.datetime.utcnow())
        return hashlib.sha1(bytes(now, "utf-8")).hexdigest()


class MissingResourceSchemaError(Exception):
    def __init__(self, resource):
        self.message = "Missing schema for resource {}".format(resource)
