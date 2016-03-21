#!/usr/bin/env python3
# vim: set fileencoding=utf8 :

import json
import sqlite3
import tornado.ioloop
from tornado.options import options, define

import momoko

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

    io_loop = tornado.ioloop.IOLoop.current()

    # connect to postgre using momoko
    #  see http://momoko.61924.nl/en/latest/tutorial.html#trival-example
    conn = momoko.Pool(
        'dbname=postgres '
        'user=postgres '
        'host=localhost '
        'port=5432',
        ioloop=io_loop
    )
    future = conn.connect()
    io_loop.add_future(future, lambda x: io_loop.stop())
    io_loop.start()
    connection = future.result()  # raises exception on connection error

    r = tornado_jsonapi.resource.DBAPI2Resource(schema, momoko, connection)
    io_loop.add_future(r._create_table(), lambda x: io_loop.stop())
    io_loop.start()
    application = tornado.web.Application([
        (
            r"/api/posts/([^/]*)",
            tornado_jsonapi.handlers.APIHandler,
            dict(resource=r)
        ),
    ], **settings)
    application.listen(8888)
    io_loop.start()


if __name__ == "__main__":
    main()
