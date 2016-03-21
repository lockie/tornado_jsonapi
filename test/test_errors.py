#!/usr/bin/env python3
# vim: set fileencoding=utf8 :

import sqlite3
import json
import status
import tornado.web
import tornado.testing
import pytest
from test import SimpleAppMixin, PostGenerator, BaseTestCase, \
    Posts, posts_schema

import tornado_jsonapi.resource
import tornado_jsonapi.exceptions


_message = 'Foo is too slow'


class TestErrors(SimpleAppMixin, PostGenerator, BaseTestCase):
    def construct_app(self):
        app = super().construct_app()

        class Handler(tornado_jsonapi.handlers.APIHandler):
            def get(self, id_=None):
                if id_:
                    r = 1 / int(id_)
                raise tornado.web.HTTPError(
                    status.HTTP_408_REQUEST_TIMEOUT,
                    _message
                )

        class Resource(Posts):
            def create(self, attributes):
                return None

            def update(self, id_, attributes):
                return None

            def delete(self, id_):
                return None

        app.add_handlers(
            r'.*',
            [(
                r'/api/v2/posts/([^/]*)',
                Handler,
                dict(resource=Resource([{'text': '', 'author': ''}]))
            )]
        )
        return app

    def test_missing_schema_exception(self):
        class MissingSchemaResource(tornado_jsonapi.resource.Resource):
            def __init__(self):
                super().__init__(posts_schema)

            def name(self):
                return 'whoopsie'

        with pytest.raises(
                tornado_jsonapi.exceptions.MissingResourceSchemaError):
            r = MissingSchemaResource()

    def test_debug_traceback(self):
        self.app.app.application.settings['serve_traceback'] = True
        resp = self.app.get('/api/v2/posts/',
                            status=status.HTTP_408_REQUEST_TIMEOUT)
        assert 'most recent call last' in resp

    def test_HTTP_exception_logging(self):
        with tornado.testing.ExpectLog('tornado.general', '.*' + _message):
            self.app.get('/api/v2/posts/',
                         status=status.HTTP_408_REQUEST_TIMEOUT)

    def test_exception_logging(self):
        with tornado.testing.ExpectLog('tornado.application', '.*Uncaught'):
            self.app.get('/api/v2/posts/0',
                         status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def test_invalid_JSON_request(self):
        self.app.post(
            '/api/posts/',
            'rawr',
            {'Content-Type': self.content_type()},
            status=status.HTTP_400_BAD_REQUEST)

    def test_invalid_object_request(self):
        res = self.app.post(
            '/api/posts/',
            json.dumps(self.generate_resource()),
            {'Content-Type': self.content_type()})
        res = self.app.get(res.location)
        post = json.loads(res.body.decode(encoding='UTF-8'))
        id_ = post['data']['id']
        self.app.patch(
            '/api/posts/' + id_,
            json.dumps({
                'data': {
                    'id': id_,
                    'attributes': {
                        # no 'author'
                        'text': self.generate_text()
                    }
                }
            }),
            {'Content-Type': self.content_type()},
            status=status.HTTP_400_BAD_REQUEST
        )

    def test_invalid_resource_request(self):
        res = self.generate_resource()
        del res['data']['attributes']
        self.app.post(
            '/api/posts/',
            json.dumps(res),
            {'Content-Type': self.content_type()},
            status=status.HTTP_400_BAD_REQUEST)

    def test_invalid_resource_attributes_request(self):
        res = self.generate_resource()
        del res['data']['attributes']['text']
        self.app.post(
            '/api/posts/',
            json.dumps(res),
            {'Content-Type': self.content_type()},
            status=status.HTTP_400_BAD_REQUEST)

    def test_POST_with_id(self):
        self.app.post(
            '/api/posts/1',
            json.dumps(self.generate_resource()),
            {'Content-Type': self.content_type()},
            status=status.HTTP_400_BAD_REQUEST)

    def test_erroneous_creation(self):
        self.app.post(
            '/api/v2/posts/',
            json.dumps(self.generate_resource()),
            {'Content-Type': self.content_type()},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def test_PATCH_missing_id(self):
        self.app.patch(
            '/api/posts/',
            json.dumps(self.generate_resource()),
            {'Content-Type': self.content_type()},
            status=status.HTTP_400_BAD_REQUEST)

    def test_PATCH_id_mismatch(self):
        res = self.app.post(
            '/api/posts/',
            json.dumps(self.generate_resource()),
            {'Content-Type': self.content_type()})
        res = self.app.get(res.location)
        id_ = json.loads(res.body.decode(encoding='UTF-8'))['data']['id']
        self.app.patch(
            '/api/posts/1',
            json.dumps({
                'data': {
                    'id': id_,
                    'type': 'post',
                    'attributes': {
                        'text': self.generate_text()
                    }
                }
            }),
            {'Content-Type': self.content_type()},
            status=status.HTTP_400_BAD_REQUEST
        )

    def test_erroneous_updating(self):
        self.app.patch(
            '/api/v2/posts/' + self.empty_id,
            json.dumps({
                'data': {
                    'id': self.empty_id,
                    'type': 'post',
                    'attributes': {
                        'text': self.generate_text()
                    }
                }
            }),
            {'Content-Type': self.content_type()},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    def test_DELETE_missing_id(self):
        self.app.delete('/api/posts/', status=status.HTTP_400_BAD_REQUEST)

    def test_DELETE_missing_resource(self):
        self.app.delete('/api/posts/1', status=status.HTTP_404_NOT_FOUND)

    def test_erroneous_deleting(self):
        self.app.delete('/api/v2/posts/' + self.empty_id,
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def test_notfound_handler(self):
        resp = self.app.get('/rawr', status=status.HTTP_404_NOT_FOUND)
        assert 'Resource not found' in resp

    def test_SQLAlchemy_compound_key(self):
        from sqlalchemy import Column, Integer, String
        from sqlalchemy.ext.declarative import declarative_base
        Base = declarative_base()

        class CompoundPost(Base):
            __tablename__ = 'posts'

            id = Column(Integer, primary_key=True)
            author = Column(String, primary_key=True)
            text = Column(String)

        with pytest.raises(NotImplementedError):
            r = tornado_jsonapi.resource.SQLAlchemyResource(CompoundPost, None)

    def test_DBAPI2_rollback(self):
        r = tornado_jsonapi.resource.DBAPI2Resource(
            posts_schema, sqlite3, sqlite3.connect(':memory:'))
        # omit _create_table()
        with pytest.raises(sqlite3.OperationalError):
            r.list_().result()
