#!/usr/bin/env python3
# vim: set fileencoding=utf8 :

""" Test MUST parts of JSON API specification
"""

import json
import status
from test import SimpleAppMixin, PostGenerator, BaseTestCase


class TestContentNegotiation(SimpleAppMixin, PostGenerator, BaseTestCase):
    def test_content_type_response(self):
        """
        Servers MUST send all JSON API data in response documents with the
        header Content-Type: application/vnd.api+json without any media type
        parameters.
        """
        # assuming header set identically for all URLS
        resp = self.app.get('/api/posts/')
        assert resp.content_type == self.content_type()

    def test_content_type_request(self):
        """
        Servers MUST respond with a 415 Unsupported Media Type status code if
        a request specifies the header Content-Type: application/vnd.api+json
        with any media type parameters.
        """
        self.app.post(
            '/api/posts/',
            params='test',  # so that body length != 0
            content_type=self.content_type() + '; supported-ext="bizzare"',
            status=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE)

    def test_accept(self):
        """
        Servers MUST respond with a 406 Not Acceptable status code if a
        request's Accept header contains the JSON API media type and all
        instances of that media type are modified with media type parameters.
        """
        self.app.get(
            '/api/posts/',
            headers={'Accept':
                     self.content_type() + '; supported-ext="bizzare"; q=1'},
            status=status.HTTP_406_NOT_ACCEPTABLE)


class TestFetchingData(SimpleAppMixin, BaseTestCase):
    def test_200(self):
        """
        A server MUST respond to a successful request to fetch an individual
        resource or resource collection with a 200 OK response.
        """
        # test individual resource, collection will be already tested in
        #  get_first_post_id()
        self.app.get('/api/posts/{}'.format(self.get_first_post_id()))

    def test_collection(self):
        """
        A server MUST respond to a successful request to fetch a resource
        collection with an array of resource objects or an empty array ([]) as
        the response document's primary data.
        """
        res = self.app.get('/api/posts/')
        posts = json.loads(res.body.decode(encoding='UTF-8'))
        assert type(posts['data']) is list

    def test_individual(self):
        """
        A server MUST respond to a successful request to fetch an individual
        resource with a resource object or null provided as the response
        document's primary data.
        """
        res = self.app.get('/api/posts/{}'.format(self.get_first_post_id()))
        post = json.loads(res.body.decode(encoding='UTF-8'))['data']
        assert type(post) is dict and 'type' in post and 'id' in post
        res = self.app.get('/api/posts/{}'.format(
            self.get_first_post_id() + '_'))
        post = json.loads(res.body.decode(encoding='UTF-8'))['data']
        assert post is None

    def test_json(self):
        """
        A JSON object MUST be at the root of every JSON API request and
        response containing data. This object defines a document's "top level".
        """
        res = self.app.get('/api/posts/')
        json.loads(res.body.decode(encoding='UTF-8'))


class TestCreatingResources(SimpleAppMixin, PostGenerator, BaseTestCase):
    def test_client_generated_id(self):
        """
        A server MUST return 403 Forbidden in response to an unsupported
        request to create a resource with a client-generated ID.
        """
        # for now, we do not support those
        self.app.post(
            '/api/posts/',
            json.dumps(self.generate_resource(None, {'id': '1'})),
            {'Content-Type': self.content_type()},
            status=status.HTTP_403_FORBIDDEN)

    def test_creating(self):
        """
        If a POST request did not include a Client-Generated ID and the
        requested resource has been created successfully, the server MUST
        return a 201 Created status code.
        """
        self.app.post(
            '/api/posts/',
            json.dumps(self.generate_resource()),
            {'Content-Type': self.content_type()},
            status=status.HTTP_201_CREATED)

    def test_creating_document(self):
        """
        The response MUST also include a document that contains the primary
        resource created.
        """
        resource = self.generate_resource()
        res = self.app.post(
            '/api/posts/',
            json.dumps(resource),
            {'Content-Type': self.content_type()},
            status=status.HTTP_201_CREATED)
        doc = json.loads(res.body.decode(encoding='UTF-8'))['data']
        assert doc['type'] == 'post'
        assert resource['data']['attributes'] == doc['attributes']

    def test_type_conflict(self):
        """
        A server MUST return 409 Conflict when processing a POST request in
        which the resource object's type is not among the type(s) that
        constitute the collection represented by the endpoint.
        """
        self.app.post(
            '/api/posts/',
            json.dumps(self.generate_resource(None, {'type': 'author'})),
            {'Content-Type': self.content_type()},
            status=status.HTTP_409_CONFLICT)


class TestUpdatingResources(SimpleAppMixin, PostGenerator, BaseTestCase):
    def test_missing_attributes(self):
        """
        If a request does not include all of the attributes for a resource, the
        server MUST interpret the missing attributes as if they were included
        with their current values. The server MUST NOT interpret missing
        attributes as null values.
        """
        id_ = self.get_first_post_id()
        res = self.app.get('/api/posts/' + id_)
        old_post = json.loads(res.body.decode(encoding='utf-8'))
        res = self.app.patch(
            '/api/posts/' + id_,
            json.dumps({
                'data': {
                    'id': id_,
                    'type': 'post',
                    'attributes': {
                        'text': self.generate_text()
                    }
                }
            }),
            {'content-type': self.content_type()}
        )
        post = json.loads(res.body.decode(encoding='utf-8'))
        assert old_post['data']['attributes']['author'] == \
            post['data']['attributes']['author']

    def test_internal_modification(self):
        """
        If a server accepts an update but also changes the resource(s) in ways
        other than those specified by the request (for example, updating the
        updated-at attribute or a computed sha), it MUST return a 200 OK
        response.
        The response document MUST include a representation of the updated
        resource(s) as if a GET request was made to the request URL.
        """
        # XXX code up-to-date case
        id_ = self.get_first_post_id()
        res = self.app.get('/api/posts/' + id_)
        old_post = json.loads(res.body.decode(encoding='UTF-8'))
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
            {'Content-Type': self.content_type()},
            status=status.HTTP_200_OK
        )
        post = json.loads(res.body.decode(encoding='UTF-8'))
        old_post['data']['attributes']['text'] = new_text
        assert old_post != post, 'Resource is up-to-date but returned in body'

    def test_404_response(self):
        """
        A server MUST return 404 Not Found when processing a request to modify
        a resource that does not exist.
        """
        id_ = self.get_first_post_id() + '_'
        self.app.patch(
            '/api/posts/' + id_,
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
            status=status.HTTP_404_NOT_FOUND
        )

    def test_type_conflict(self):
        """
        A server MUST return 409 Conflict when processing a PATCH request in
        which the resource object's type and id do not match the server's
        endpoint.
        """
        id_ = self.get_first_post_id()
        self.app.patch(
            '/api/posts/' + id_,
            json.dumps({
                'data': {
                    'id': id_,
                    'type': 'author',
                    'attributes': {
                        'text': self.generate_text()
                    }
                }
            }),
            {'Content-Type': self.content_type()},
            status=status.HTTP_409_CONFLICT
        )


class TestDeletingResources(SimpleAppMixin, BaseTestCase):
    def test_deleting(self):
        """
        A server MUST return a 204 No Content status code if a deletion request
        is successful and no content is returned.
        """
        res = self.app.delete('/api/posts/{}'.format(self.get_first_post_id()),
                              status=status.HTTP_204_NO_CONTENT)
        assert len(res.body) == 0
