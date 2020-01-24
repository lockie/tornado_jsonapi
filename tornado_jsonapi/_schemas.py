#!/usr/bin/env python3
# vim: set fileencoding=utf8 :

import jsl
import python_jsonschema_objects as pjs
import inflection


class Meta(jsl.Document):
    class Options(object):
        definition_id = "meta"
        additional_properties = True


class Link(jsl.Document):
    href = jsl.UriField(required=True)
    meta = jsl.DocumentField(Meta, as_ref=True)

    class Options(object):
        definition_id = "link"


class Links(jsl.Document):
    self = jsl.UriField()
    related = jsl.DocumentField(Link, as_ref=True)

    class Options(object):
        definition_id = "links"
        additional_properties = True


class PostResource(jsl.Document):
    type = jsl.StringField(required=True)
    id = jsl.StringField()
    attributes = jsl.DictField(additional_properties=True)
    links = jsl.DocumentField(Links, as_ref=True)
    meta = jsl.DocumentField(Meta, as_ref=True)

    class Options(object):
        definition_id = "resource"


class PostData(jsl.Document):
    data = jsl.DocumentField(PostResource, as_ref=True)

    class Options(object):
        title = "Data"
        definition_id = "data"


class PatchResource(jsl.Document):
    type = jsl.StringField(required=True)
    id = jsl.StringField(required=True)
    attributes = jsl.DictField(additional_properties=True)
    links = jsl.DocumentField(Links, as_ref=True)
    meta = jsl.DocumentField(Meta, as_ref=True)

    class Options(object):
        definition_id = "resource"


class PatchData(jsl.Document):
    data = jsl.DocumentField(PatchResource, as_ref=True)

    class Options(object):
        title = "Data"
        definition_id = "data"


def _build_schema(cls):
    builder = pjs.ObjectBuilder(cls.get_schema())
    classes = builder.build_classes()
    name = inflection.camelize(cls.get_definition_id())
    return classes[name]


_postDataSchema = None


def postDataSchema():
    global _postDataSchema
    if _postDataSchema is None:
        _postDataSchema = _build_schema(PostData)
    return _postDataSchema


_patchDataSchema = None


def patchDataSchema():
    global _patchDataSchema
    if _patchDataSchema is None:
        _patchDataSchema = _build_schema(PatchData)
    return _patchDataSchema
