#!/usr/bin/env python3
# vim: set fileencoding=utf8 :

import hashlib
import json
import tornado.ioloop
from tornado.options import options, define
from tornado import gen

import tornado_jsonapi.resource
import tornado_jsonapi.handlers


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
        super().__init__(schema)

    def name(self):
        return 'post'

    @gen.coroutine
    def create(self, attributes):
        self.data.append(attributes)
        return Posts.ResourceObject(self, attributes)

    @gen.coroutine
    def read(self, id_):
        for p in self.data:
            post = Posts.ResourceObject(self, p)
            if post.id_() == id_:
                return post

    @gen.coroutine
    def update(self, id_, attributes):
        for p in self.data:
            post = Posts.ResourceObject(self, p)
            if post.id_() == id_:
                p.update(attributes)
                return post

    @gen.coroutine
    def delete(self, id_):
        for p in self.data:
            post = Posts.ResourceObject(self, p)
            if post.id_() == id_:
                self.data.remove(p)
                return True
        return False

    @gen.coroutine
    def list_(self, limit=0, page=0):
        return [Posts.ResourceObject(self, p) for p in self.data]

    @gen.coroutine
    def list_count_(self):
        return len(self.data)


def main():
    define("debug", default=False, help="Run in debug mode")
    options.parse_command_line()
    settings = {}
    settings.update(options.group_dict(None))
    settings.update(tornado_jsonapi.handlers.not_found_handling_settings())
    application = tornado.web.Application([
        (
            r"/api/posts/([^/]*)",
            tornado_jsonapi.handlers.APIHandler,
            dict(resource=Posts(json.loads(open('data.json').read())))
        ),
    ], **settings)
    application.listen(8888)
    tornado.ioloop.IOLoop.current().start()


if __name__ == "__main__":
    main()
