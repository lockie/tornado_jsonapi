#!/usr/bin/env python3
# vim: set fileencoding=utf8 :

import json
import sqlite3
import tornado.ioloop
from tornado.options import options, define

import tornado_jsonapi.handlers
import tornado_jsonapi.resource


schema = json.loads("""
    {
        "$schema": "http://json-schema.org/draft-04/schema#",
        "title": "post",
        "description": "Example blog post API for tornado_jsonapi",
        "type": "object",
        "properties": {
            "text":
            {
                "type": "string",
                "description": "post body"
            },
            "author":
            {
                "type": "string",
                "description": "author name"
            }
        },
        "required": [ "text", "author" ],
        "additionalProperties": false
    }
""")


def main():
    define("debug", default=False, help="Run in debug mode")
    options.parse_command_line()
    settings = {}
    settings.update(options.group_dict(None))
    settings.update(tornado_jsonapi.handlers.not_found_handling_settings())

    r = tornado_jsonapi.resource.DBAPI2Resource(
        schema, sqlite3, sqlite3.connect(':memory:'))
    r._create_table()
    application = tornado.web.Application([
        (
            r"/api/posts/([^/]*)",
            tornado_jsonapi.handlers.APIHandler,
            dict(resource=r)
        ),
    ], **settings)
    application.listen(8888)
    tornado.ioloop.IOLoop.current().start()


if __name__ == "__main__":
    main()
