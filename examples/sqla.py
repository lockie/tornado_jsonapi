#!/usr/bin/env python3
# vim: set fileencoding=utf8 :

import tornado.ioloop
from tornado.options import options, define

from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

import tornado_jsonapi.handlers
import tornado_jsonapi.resource


Base = declarative_base()


class Post(Base):
    __tablename__ = 'posts'

    id = Column(Integer, primary_key=True)
    author = Column(String)
    text = Column(String)


def main():
    define("debug", default=False, help="Run in debug mode")
    options.parse_command_line()
    settings = {}
    settings.update(options.group_dict(None))
    settings.update(tornado_jsonapi.handlers.not_found_handling_settings())

    engine = create_engine('sqlite:///:memory:', echo=settings['debug'])
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    application = tornado.web.Application([
        (
            r"/api/posts/([^/]*)",
            tornado_jsonapi.handlers.APIHandler,
            dict(resource=tornado_jsonapi.resource.SQLAlchemyResource(
                Post, Session))
        ),
    ], **settings)
    application.listen(8888)
    tornado.ioloop.IOLoop.current().start()


if __name__ == "__main__":
    main()
