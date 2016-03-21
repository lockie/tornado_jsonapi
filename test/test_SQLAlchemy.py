#!/usr/bin/env python3
# vim: set fileencoding=utf8 :

import json
import status
from test import SQLAlchemyMixin, PostGenerator, BaseTestCase


class TestSQLAlchemyResource(SQLAlchemyMixin, PostGenerator, BaseTestCase):
    def test_create(self):
        self.app.post(
            '/api/posts/',
            json.dumps(self.generate_resource()),
            {'Content-Type': self.content_type()},
            status=status.HTTP_201_CREATED)

    def test_read(self):
        post = self.generate_resource()
        res = self.app.post(
            '/api/posts/',
            json.dumps(post),
            {'Content-Type': self.content_type()})
        res = self.app.get(res.location)
        new_post = json.loads(res.body.decode(encoding='UTF-8'))['data']
        assert post['data']['type'] == new_post['type']
        assert post['data']['attributes'] == new_post['attributes']

    def test_update(self):
        res = self.app.post(
            '/api/posts/',
            json.dumps(self.generate_resource()),
            {'Content-Type': self.content_type()})
        res = self.app.get(res.location)
        old_post = json.loads(res.body.decode(encoding='UTF-8'))
        id_ = old_post['data']['id']
        new_text = self.generate_text()
        res = self.app.patch(
            '/api/posts/' + id_,
            json.dumps({
                'data': {
                    'id': id_,
                    'type': 'post',
                    'attributes': {
                        'text': new_text
                    }
                }
            }),
            {'Content-Type': self.content_type()}
        )
        post = json.loads(res.body.decode(encoding='UTF-8'))
        assert post['data']['id'] == old_post['data']['id']
        assert post['data']['type'] == old_post['data']['type']
        assert post['data']['attributes']['author'] == \
            old_post['data']['attributes']['author']
        assert post['data']['attributes']['text'] != \
            old_post['data']['attributes']['text']

    def test_delete(self):
        res = self.app.post(
            '/api/posts/',
            json.dumps(self.generate_resource()),
            {'Content-Type': self.content_type()})
        res = self.app.get(res.location)
        post = json.loads(res.body.decode(encoding='UTF-8'))
        id_ = post['data']['id']
        self.app.delete('/api/posts/{}'.format(id_),
                        status=status.HTTP_204_NO_CONTENT)
        res = self.app.get('/api/posts/' + id_)
        # XXX non-nullable?
        assert json.loads(res.body.decode(encoding='UTF-8'))['data'] is None

    def test_list(self):
        self.app.post('/api/posts/', json.dumps(self.generate_resource()),
                      {'Content-Type': self.content_type()})
        self.app.post('/api/posts/', json.dumps(self.generate_resource()),
                      {'Content-Type': self.content_type()})
        res = self.app.get('/api/posts/')
        post = json.loads(res.body.decode(encoding='UTF-8'))
        assert len(post['data']) == 2
