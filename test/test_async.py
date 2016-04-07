#!/usr/bin/env python3
# vim: set fileencoding=utf8 :

import os
import time
import socket
import json
import status
import tornado.web
from tornado import gen
import tornado_jsonapi.resource
from tornado.httpclient import AsyncHTTPClient, HTTPRequest
from tornado.testing import AsyncHTTPTestCase, gen_test
import pytest
from test import SlowAppMixin, PostGenerator, BaseTestCase, posts_schema


class TestAsynchronous(SlowAppMixin, PostGenerator, BaseTestCase):
    def setUp(self):
        # NB: this is only required when mixing several DBAPIs in one app
        import dbapiext
        dbapiext._query_cache.clear()

        self.http_client = AsyncHTTPClient()
        AsyncHTTPTestCase.setUp(self)

    def test_create(self):
        self.http_client.fetch(
            HTTPRequest(
                'http://localhost:{}/api/posts/'.format(
                    self.get_http_port()),
                method='POST',
                headers={'Content-Type': self.content_type()},
                body=json.dumps(self.generate_resource())
            ),
            callback=self.stop)
        self.http_client.fetch(
            'http://localhost:{}/api/posts/'.format(self.get_http_port()),
            callback=self.stop)
        res = self.wait()
        assert res.effective_url.endswith('/api/posts/'),\
            'Requests are not asynchronous'
        res = self.wait()
        assert res.code == status.HTTP_201_CREATED,\
            'Interrupted async request is corrupted'

    def test_read(self):
        self.http_client.fetch(
            'http://localhost:{}/api/posts/{}'.format(
                self.get_http_port(),
                self.empty_id
            ),
            callback=self.stop)
        self.http_client.fetch(
            'http://localhost:{}/api/posts/'.format(self.get_http_port()),
            callback=self.stop)
        res = self.wait()
        assert res.effective_url.endswith('/api/posts/'),\
            'Requests are not asynchronous'
        res = self.wait()
        assert 'author' in res.buffer.getvalue().decode(encoding='utf-8'),\
            'Interrupted async request is corrupted'

    def test_update(self):
        post = self.generate_resource()
        post['data']['id'] = self.empty_id
        self.http_client.fetch(
            HTTPRequest(
                'http://localhost:{}/api/posts/{}'.format(
                    self.get_http_port(),
                    self.empty_id
                ),
                method='PATCH',
                headers={'Content-Type': self.content_type()},
                body=json.dumps(post)
            ),
            callback=self.stop)
        self.http_client.fetch(
            'http://localhost:{}/api/posts/'.format(self.get_http_port()),
            callback=self.stop)
        res = self.wait()
        assert res.effective_url.endswith('/api/posts/'),\
            'Requests are not asynchronous'
        res = self.wait()
        assert post['data']['attributes']['author'] in\
            res.buffer.getvalue().decode(encoding='utf-8'),\
            'Interrupted async request is corrupted'

    def test_delete(self):
        self.http_client.fetch(
            HTTPRequest(
                'http://localhost:{}/api/posts/{}'.format(
                    self.get_http_port(),
                    self.empty_id
                ),
                method='DELETE'
            ),
            callback=self.stop)
        self.http_client.fetch(
            'http://localhost:{}/api/posts/'.format(self.get_http_port()),
            callback=self.stop)
        res = self.wait()
        assert res.effective_url.endswith('/api/posts/'),\
            'Requests are not asynchronous'
        res = self.wait()
        assert res.code == status.HTTP_204_NO_CONTENT,\
            'Interrupted async request is corrupted'


no_postgre = True
try:
    import momoko
    import docker
    no_postgre = False
except ImportError:
    pass


@pytest.mark.skipif(no_postgre, reason='Missing dependencies for PostgreSQL')
class TestPostgre(PostGenerator, BaseTestCase):
    @classmethod
    def setup_class(cls):
        api = os.getenv('DOCKER_API')
        if api is not None:
            cls.docker_client = docker.Client('unix://var/run/docker.sock',
                                              version=api)
        else:
            cls.docker_client = docker.Client('unix://var/run/docker.sock')
        container = cls.docker_client.create_container(image='postgres')
        cls.container_id = container['Id']
        cls.docker_client.start(cls.container_id, network_mode='host')

        # wait for postgre daemon to be up
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        while sock.connect_ex(('127.0.0.1', 5432)) != 0:
            pass
        sock.close()
        time.sleep(1)  # wait for blue elephant

    @classmethod
    def teardown_class(cls):
        cls.docker_client.stop(cls.container_id)
        pass

    def setUp(self):
        # NB: this is only required when mixing several DBAPIs in one app
        import dbapiext
        dbapiext._query_cache.clear()

        self.http_client = AsyncHTTPClient()
        AsyncHTTPTestCase.setUp(self)

    def construct_app(self):
        class SlowpokeResource(tornado_jsonapi.resource.DBAPI2Resource):
            @gen.coroutine
            def sleep(self):
                conn = yield self.connection.getconn()
                with self.connection.manage(conn):
                    yield conn.execute('select pg_sleep(1)')

            @gen.coroutine
            def create(self, attributes):
                yield self.sleep()
                return super().create(attributes)

            @gen.coroutine
            def read(self, id_):
                yield self.sleep()
                return super().read(id_)

            @gen.coroutine
            def update(self, id_, attributes):
                yield self.sleep()
                return super().update(id_, attributes)

            @gen.coroutine
            def delete(self, id_):
                yield self.sleep()
                return super().delete(id_)

            @gen.coroutine
            def list_(self):
                r = super().list_()
                return r

        # connect to postgre using momoko
        #  see http://momoko.61924.nl/en/latest/tutorial.html#trival-example
        conn = momoko.Pool(
            'dbname=postgres '
            'user=postgres '
            'host=localhost '
            'port=5432',
            ioloop=self.io_loop
        )
        future = conn.connect()
        self.io_loop.add_future(future, lambda x: self.io_loop.stop())
        self.io_loop.start()
        connection = future.result()  # raises exception on connection error

        resource = SlowpokeResource(posts_schema, momoko, connection)
        self.io_loop.add_future(resource._create_table(),
                                lambda x: self.io_loop.stop())
        self.io_loop.start()

        app = tornado.web.Application([
            (
                r"/api/posts/([^/]*)",
                tornado_jsonapi.handlers.APIHandler,
                dict(resource=resource)
            ),
        ], **tornado_jsonapi.handlers.not_found_handling_settings())
        return app

    def create_post(self):
        self.http_client.fetch(
            HTTPRequest(
                'http://localhost:{}/api/posts/'.format(
                    self.get_http_port()),
                method='POST',
                headers={'Content-Type': self.content_type()},
                body=json.dumps(self.generate_resource())
            ),
            callback=self.stop)
        res = self.wait()
        post = json.loads(res.buffer.getvalue().decode(encoding='utf-8'))
        return post['data']['id']

    def test_create(self):
        self.http_client.fetch(
            HTTPRequest(
                'http://localhost:{}/api/posts/'.format(
                    self.get_http_port()),
                method='POST',
                headers={'Content-Type': self.content_type()},
                body=json.dumps(self.generate_resource())
            ),
            callback=self.stop)
        self.http_client.fetch(
            'http://localhost:{}/api/posts/'.format(self.get_http_port()),
            callback=self.stop)
        res = self.wait()
        assert res.effective_url.endswith('/api/posts/'),\
            'Requests are not asynchronous'
        res = self.wait()
        assert res.code == status.HTTP_201_CREATED,\
            'Interrupted async request is corrupted'

    def test_read(self):
        id_ = self.create_post()
        self.http_client.fetch(
            'http://localhost:{}/api/posts/{}'.format(
                self.get_http_port(),
                id_
            ),
            callback=self.stop)
        self.http_client.fetch(
            'http://localhost:{}/api/posts/'.format(self.get_http_port()),
            callback=self.stop)
        res = self.wait()
        assert res.effective_url.endswith('/api/posts/'),\
            'Requests are not asynchronous'
        res = self.wait()
        assert 'author' in res.buffer.getvalue().decode(encoding='utf-8'),\
            'Interrupted async request is corrupted'

    def test_update(self):
        id_ = self.create_post()
        post = self.generate_resource()
        post['data']['id'] = id_
        self.http_client.fetch(
            HTTPRequest(
                'http://localhost:{}/api/posts/{}'.format(
                    self.get_http_port(),
                    id_
                ),
                method='PATCH',
                headers={'Content-Type': self.content_type()},
                body=json.dumps(post)
            ),
            callback=self.stop)
        self.http_client.fetch(
            'http://localhost:{}/api/posts/'.format(self.get_http_port()),
            callback=self.stop)
        res = self.wait()
        assert res.effective_url.endswith('/api/posts/'),\
            'Requests are not asynchronous'
        res = self.wait()
        assert post['data']['attributes']['author'] in\
            res.buffer.getvalue().decode(encoding='utf-8'),\
            'Interrupted async request is corrupted'

    def test_delete(self):
        id_ = self.create_post()
        self.http_client.fetch(
            HTTPRequest(
                'http://localhost:{}/api/posts/{}'.format(
                    self.get_http_port(),
                    id_
                ),
                method='DELETE'
            ),
            callback=self.stop)
        self.http_client.fetch(
            'http://localhost:{}/api/posts/'.format(self.get_http_port()),
            callback=self.stop)
        res = self.wait()
        assert res.effective_url.endswith('/api/posts/'),\
            'Requests are not asynchronous'
        res = self.wait()
        assert res.code == status.HTTP_204_NO_CONTENT,\
            'Interrupted async request is corrupted'
