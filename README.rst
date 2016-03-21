Tornado_jsonapi
---------------
Tornado_jsonapi is a library for creating JSON API (as per
`jsonapi.org <http://jsonapi.org/>`_ specification) using
`Tornado <http://tornadoweb.org>`_ web framework. It features

- semi-automatic API generation using provided
  `JSON schema <http://json-schema.org>`_ of resource;
- support for arbitrary data sources, including SQLAlchemy and PostgreSQL (via
  DBAPI2 support layer);
- support for asynchronous data source operations;
- strict `jsonapi.org <http://jsonapi.org/>`_ specification conformance.

Usage
-----

.. code-block:: python

    import sqlite3
    import tornado.ioloop
    import tornado.web
    import tornado_jsonapi.handlers
    import tornado_jsonapi.resource

    schema = {
        "title": "post",
        "properties": {
            "text":
            {
                "type": "string"
            },
            "author":
            {
                "type": "string"
            }
        }
    }

    res = tornado_jsonapi.resource.DBAPI2Resource(
        schema, sqlite3, sqlite3.connect(':memory:'))
    res._create_table()

    application = tornado.web.Application([
        (
            r"/api/posts/([^/]*)",
            tornado_jsonapi.handlers.APIHandler,
            dict(resource=res)
        )
    ])
    application.listen(8888)
    tornado.ioloop.IOLoop.current().start()



Installation
------------

.. code-block:: bash

    $ pip install tornado_jsonapi


Documentation
-------------

https://tornado_jsonapi.readthedocs.org


Roadmap
-------

a.k.a. TODO

- improve documentation :pensive:
- automatic API doc generation based on JSON schema;
- MongoDB/Motor support;
- support for API testing.

License
-------
This project is licensed under the MIT License.
