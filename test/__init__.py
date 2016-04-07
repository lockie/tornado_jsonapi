#!/usr/bin/env python3
# vim: set fileencoding=utf8 :

import string
import random
import loremipsum
import hashlib
import json
import sqlite3
import socket
import tornado.web
import tornado.ioloop
import webtest
from tornado import gen
import tornado.testing
from tornado import netutil
from tornado.testing import AsyncHTTPTestCase
from tornado.wsgi import WSGIAdapter
from http.cookiejar import CookieJar

import tornado_jsonapi.handlers
import tornado_jsonapi.resource


posts_schema = json.loads("""
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


class PostGenerator:
    def generate_text(self):
        return ''.join(loremipsum.get_sentences(1))

    def generate_post(self):
        author = ''.join([random.choice(string.ascii_lowercase)
                          for i in range(5)])
        return {'author': author, 'text': self.generate_text()}

    def generate_resource(self, post=None, additional_data=None):
        if post is None:
            post = self.generate_post()
        data = {'type': 'post', 'attributes': post}
        if additional_data is not None:
            data.update(additional_data)
        return {'data': data}


class BaseTestCase(AsyncHTTPTestCase):
    ''' Base class for all test cases.
    We need to derive from AsyncTestCase for it creates tornado IOLoop
    impicitly.
    '''

    empty_id = 'da39a3ee5e6b4b0d3255bfef95601890afd80709'

    def __init__(self, *args, **kwargs):
        AsyncHTTPTestCase.__init__(self, *args, **kwargs)
        self.maxDiff = None
        self._app = None

    def construct_app(self):
        raise NotImplementedError

    def get_app(self):
        if self._app is None:
            app = self.construct_app()
            app.io_loop = self.io_loop
            return app
        else:
            return self._app

    def content_type(self):
        return 'application/vnd.api+json'

    def setUp(self):
        AsyncHTTPTestCase.setUp(self)
        self.app = webtest.TestApp(
            WSGIAdapter(self.get_app()),
            cookiejar=CookieJar())


class Posts(tornado_jsonapi.resource.Resource):
    class ResourceObject:
        def __init__(self, resource, data):
            self.resource = resource
            self.data = data

        def id_(self):
            hsh = hashlib.sha1()
            values = [self.data[attr] for attr in sorted(self.data)]
            for v in values:
                hsh.update(bytes(str(v), 'utf-8'))
            return hsh.hexdigest()

        def type_(self):
            return 'post'

        def attributes(self):
            return self.data

    def __init__(self, data):
        self.data = data
        super().__init__(posts_schema)

    def name(self):
        return 'post'

    def create(self, attributes):
        self.data.append(attributes)
        return Posts.ResourceObject(self, attributes)

    def read(self, id_):
        for p in self.data:
            post = Posts.ResourceObject(self, p)
            if post.id_() == id_:
                return post

    def update(self, id_, attributes):
        for p in self.data:
            post = Posts.ResourceObject(self, p)
            if post.id_() == id_:
                p.update(attributes)
                return post  # XXX ?

    def delete(self, id_):
        for p in self.data:
            post = Posts.ResourceObject(self, p)
            if post.id_() == id_:
                self.data.remove(p)
                return True
        return False

    def list_(self):
        return [Posts.ResourceObject(self, p) for p in self.data]


class SimpleAppMixin:
    def construct_app(self):
        data = """
        [
            {
                "text": "RAWR I'm a lion",
                "author": "Andrew"
            },
            {
                "text": "я - лѣвъ!",
                "author": "Андрей"
            }
        ]
        """
        app = tornado.web.Application([
            (
                r"/api/posts/([^/]*)",
                tornado_jsonapi.handlers.APIHandler,
                dict(resource=Posts(json.loads(data)))
            ),
        ], **tornado_jsonapi.handlers.not_found_handling_settings())
        return app

    def get_first_post_id(self):
        res = self.app.get('/api/posts/')
        posts = json.loads(res.body.decode(encoding='utf-8'))
        return posts['data'][0]['id']


class SQLAlchemyMixin:
    def construct_app(self):
        from sqlalchemy import create_engine, Column, Integer, String
        from sqlalchemy.ext.declarative import declarative_base
        from sqlalchemy.orm import sessionmaker
        engine = create_engine('sqlite:///:memory:', echo=True)
        Base = declarative_base()

        class Post(Base):
            __tablename__ = 'posts'

            id = Column(Integer, primary_key=True)
            author = Column(String)
            text = Column(String)

        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)

        app = tornado.web.Application([
            (
                r"/api/posts/([^/]*)",
                tornado_jsonapi.handlers.APIHandler,
                dict(resource=tornado_jsonapi.resource.SQLAlchemyResource(
                    Post, Session))
            ),
        ], **tornado_jsonapi.handlers.not_found_handling_settings())
        return app


class DBAPI2Mixin:
    def construct_app(self):
        resource = tornado_jsonapi.resource.DBAPI2Resource(
            posts_schema, sqlite3, sqlite3.connect(':memory:'))
        resource._create_table()
        app = tornado.web.Application([
            (
                r"/api/posts/([^/]*)",
                tornado_jsonapi.handlers.APIHandler,
                dict(resource=resource)
            ),
        ], **tornado_jsonapi.handlers.not_found_handling_settings())
        return app


class SlowpokePosts(tornado_jsonapi.resource.Resource):
    class ResourceObject:
        def __init__(self, resource, data):
            self.resource = resource
            self.data = data

        def id_(self):
            hsh = hashlib.sha1()
            values = [self.data[attr] for attr in sorted(self.data)]
            for v in values:
                hsh.update(bytes(str(v), 'utf-8'))
            return hsh.hexdigest()

        def type_(self):
            return 'post'

        def attributes(self):
            return self.data

    def __init__(self, data):
        self.data = data
        super().__init__(posts_schema)

    def name(self):
        return 'post'

    @gen.coroutine
    def create(self, attributes):
        yield gen.sleep(1)
        self.data.append(attributes)
        return Posts.ResourceObject(self, attributes)

    @gen.coroutine
    def read(self, id_):
        yield gen.sleep(1)
        for p in self.data:
            post = Posts.ResourceObject(self, p)
            if post.id_() == id_:
                return post

    @gen.coroutine
    def update(self, id_, attributes):
        yield gen.sleep(1)
        for p in self.data:
            post = Posts.ResourceObject(self, p)
            if post.id_() == id_:
                p.update(attributes)
                return post  # XXX ?

    @gen.coroutine
    def delete(self, id_):
        yield gen.sleep(1)
        for p in self.data:
            post = Posts.ResourceObject(self, p)
            if post.id_() == id_:
                self.data.remove(p)
                return True
        return False

    @gen.coroutine
    def list_(self):
        return [Posts.ResourceObject(self, p) for p in self.data]


class SlowAppMixin:
    def construct_app(self):
        data = """
        [
            {
                "text": "",
                "author": ""
            },
            {
                "text": "RAWR I'm a lion",
                "author": "Andrew"
            },
            {
                "text": "я - лѣвъ!",
                "author": "Андрей"
            }
        ]
        """

        app = tornado.web.Application([
            (
                r"/api/posts/([^/]*)",
                tornado_jsonapi.handlers.APIHandler,
                dict(resource=SlowpokePosts(json.loads(data)))
            ),
        ], **tornado_jsonapi.handlers.not_found_handling_settings())
        return app

    def get_first_post_id(self):
        res = self.app.get('/api/posts/')
        posts = json.loads(res.body.decode(encoding='utf-8'))
        return posts['data'][0]['id']


def _bind_unused_port(reuse_port=False):
    '''
    See https://github.com/tornadoweb/tornado/pull/1574

    '''
    sock = netutil.bind_sockets(None, '127.0.0.1', family=socket.AF_INET,
                                reuse_port=reuse_port)[0]
    port = sock.getsockname()[1]
    return sock, port


tornado.testing.bind_unused_port = _bind_unused_port
