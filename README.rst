Tornado_jsonapi
---------------

|Build Status| |Coverage Status| |Requirements Status| |PyPi version| |Documentation Status| |GitHub License|

Tornado_jsonapi is a Python 3.3+ library for creating JSON API (as per
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

.. |Build Status| image:: https://img.shields.io/travis/lockie/tornado_jsonapi/master.svg?style=flat
     :target: https://travis-ci.org/lockie/tornado_jsonapi
.. |Coverage Status| image:: https://img.shields.io/codecov/c/github/lockie/tornado_jsonapi/master.svg?style=flat
     :target: https://codecov.io/github/lockie/tornado_jsonapi
.. |Requirements Status| image:: https://requires.io/github/lockie/tornado_jsonapi/requirements.svg?branch=master&style=flat
     :target: https://requires.io/github/lockie/tornado_jsonapi/requirements/?branch=master
.. |PyPi version| image:: https://img.shields.io/pypi/v/tornado_jsonapi.svg?style=flat
     :target: https://pypi.python.org/pypi/tornado_jsonapi
.. |Documentation Status| image:: https://readthedocs.org/projects/tornado-jsonapi/badge/?version=stable
     :target: http://tornado-jsonapi.readthedocs.org/en/stable/?badge=stable
.. |GitHub License| image:: https://img.shields.io/badge/license-MIT-blue.svg?style=flat
     :target: https://raw.githubusercontent.com/lockie/tornado_jsonapi/master/LICENSE
