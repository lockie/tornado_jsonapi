#!/usr/bin/env python3
# vim: set fileencoding=utf8 :

import types
from contextlib import contextmanager
from tornado import gen
from tornado.concurrent import Future, is_future
import inflection
import python_jsonschema_objects as pjs

from tornado_jsonapi.exceptions import MissingResourceSchemaError


class Resource:
    class ResourceObject:
        def id_(self):
            raise NotImplementedError

        def type_(self):
            raise NotImplementedError

        def attributes(self):
            raise NotImplementedError

        # TODO : relationships, links, meta

    def __init__(self, schema):
        self.schema = schema
        builder = pjs.ObjectBuilder(self.schema)
        classes = builder.build_classes()
        name = inflection.camelize(self.name())
        if name not in classes:
            raise MissingResourceSchemaError(name)
        self._schema = classes[name]

    def _on_request_end(self):
        pass

    def name(self):
        raise NotImplementedError

    def exists(self, id_):
        return self.read(id_) is not None

    def create(self, attributes):
        raise NotImplementedError

    def read(self, id_):
        raise NotImplementedError

    def update(self, id_, attributes):
        raise NotImplementedError

    def delete(self, id_):
        raise NotImplementedError

    def list_(self, limit=0, page=0):
        raise NotImplementedError

    def list_count(self):
        raise NotImplementedError


try:
    import sqlalchemy
    import alchemyjsonschema
    import alchemyjsonschema.dictify
except ImportError:
    pass


class SQLAlchemyResource(Resource):
    class ResourceObject:
        def __init__(self, resource, model, blacklist=None):
            self.resource = resource
            self.model = model
            self.blacklist = blacklist
            if self.blacklist is None:
                self.blacklist = []

        def id_(self):
            return str(
                self.model.__getattribute__(self.resource._primary_columns[0])
            )

        def type_(self):
            return self.resource.name()

        def attributes(self):
            attributes_ = alchemyjsonschema.dictify.jsonify(
                self.model, self.resource.schema
            )
            for key in self.blacklist:
                attributes_.pop(key, None)
            return attributes_

    def __init__(self, model_cls, sessionmaker):
        self._primary_columns = model_cls.__table__.primary_key.columns.keys()
        if len(self._primary_columns) > 1:
            raise NotImplementedError("Compound primary keys not supported")
        self.model_cls = model_cls
        self.model_primary_key = getattr(
            self.model_cls, self._primary_columns[0]
        )
        self.sessionmaker = sessionmaker
        self.session = sqlalchemy.orm.scoped_session(sessionmaker)
        self.blacklist = []
        factory = alchemyjsonschema.SchemaFactory(
            alchemyjsonschema.StructuralWalker
        )
        schema = factory(self.model_cls, excludes=self._primary_columns)
        super().__init__(schema)

    def _on_request_end(self):
        self.session.remove()

    def _id_filter(self, id_):
        return {self._primary_columns[0]: id_}

    def name(self):
        return inflection.camelize(
            self.model_cls.__name__, uppercase_first_letter=False
        )

    def exists(self, id_):
        return self.session.query(
            self.session.query(self.model_cls)
            .filter_by(**self._id_filter(id_))
            .exists()
        ).scalar()

    def create(self, attributes):
        model = self.model_cls(**attributes)
        self.session.add(model)
        self.session.commit()
        return SQLAlchemyResource.ResourceObject(
            self, model, blacklist=self.blacklist
        )

    def read(self, id_):
        model = (
            self.session.query(self.model_cls)
            .filter_by(**self._id_filter(id_))
            .one_or_none()
        )
        return (
            None
            if model is None
            else SQLAlchemyResource.ResourceObject(
                self, model, blacklist=self.blacklist
            )
        )

    def update(self, id_, attributes):
        model = (
            self.session.query(self.model_cls)
            .filter_by(**self._id_filter(id_))
            .one()
        )
        for k, v in attributes.items():
            setattr(model, k, v)
        self.session.merge(model)
        self.session.commit()
        return SQLAlchemyResource.ResourceObject(
            self, model, blacklist=self.blacklist
        )

    def delete(self, id_):
        # TODO shouldnt it be
        #  http://docs.sqlalchemy.org/en/latest/core/tutorial.html#deletes
        r = (
            self.session.query(self.model_cls)
            .filter_by(**self._id_filter(id_))
            .delete()
        )
        self.session.commit()
        return r

    def list_count(self):
        return self.session.query(
            sqlalchemy.func.count(self.model_primary_key)
        ).scalar()

    def list_(self, limit=0, page=0):
        if limit > 0:
            start = abs(page) * limit
            stop = start + limit
            models = self.session.query(self.model_cls).slice(start, stop)
        else:
            models = self.session.query(self.model_cls)
        res = []
        for model in models:
            res.append(
                SQLAlchemyResource.ResourceObject(
                    self, model, blacklist=self.blacklist
                )
            )
        return res


try:
    import dbapiext
except ImportError:
    pass


@gen.coroutine
def dbapi2Cursor(connection, transaction=False):
    @contextmanager
    def wrapper(connection, transaction):
        cursor = connection.cursor()
        try:
            yield cursor
            if transaction:
                connection.commit()
        except:
            if transaction:
                connection.rollback()
            raise
        finally:
            cursor.close()

    return wrapper(connection, transaction)


@gen.coroutine
def momokoCursor(pool, transaction=False):
    class wrapper:
        def __init__(self, pool, connection, transaction):
            self.pool = pool
            self.connection = connection
            self.transaction = transaction

        def __enter__(self):
            return self.connection

        @gen.coroutine
        def __exit__(self, type_, value, traceback):
            if self.transaction:
                if type_ is None:
                    yield self.connection.execute("COMMIT")
                else:
                    yield self.connection.execute("ROLLBACK")
            self.pool.putconn(self.connection)

    connection = yield pool.getconn(ping=False)
    if transaction:
        yield connection.execute("BEGIN")
    return wrapper(pool, connection, transaction)


class DBAPI2Resource(Resource):
    _types_mapping = {
        "boolean": "boolean",
        "integer": "integer",
        "number": "numeric",
        "string": "text",
    }

    class ResourceObject:
        def __init__(self, resource, row):
            self._resource = resource
            assert row is not None
            self.row = row

        def id_(self):
            return str(self.row[-1])

        def type_(self):
            return self._resource.name()

        def attributes(self):
            return {
                n: v for (n, v) in zip(self._resource.columns, self.row[:-1])
            }

    def __init__(self, schema, dbapi, connection):
        self.cursor = dbapi2Cursor
        self.connection = connection
        self.dbapi = dbapi
        if dbapi.__name__ == "momoko":
            self.cursor = momokoCursor
            self.dbapi = dbapi.psycopg2
        dbapiext.set_paramstyle(self.dbapi)
        self._tablename = inflection.pluralize(schema["title"])
        super().__init__(schema)
        self.columns = list(self._schema()._properties.keys())

    def _is_sqlite(self):
        return self.dbapi.__name__ == "sqlite3"

    def _is_postgresql(self):
        return self.dbapi.__name__ == "psycopg2"

    def _create_primary_key(self):
        id_type = "integer"
        if self._is_postgresql():
            id_type = "bigserial"
        key = "id {} not null primary key".format(id_type)
        if self._is_sqlite():
            key += " autoincrement"
        return key

    @gen.coroutine
    def _create_table(self):
        types = [
            self._types_mapping[self._schema.propinfo(c)["type"]] +
            (" not null" if c in self._schema.__required__ else "")
            for c in self.columns
        ]
        column_defs = [self._create_primary_key()] + [
            "{} {}".format(c, t) for c, t in zip(self.columns, types)
        ]
        with (yield self.cursor(self.connection, transaction=True)) as cursor:
            cur = dbapiext.execute_f(
                cursor,
                "create table if not exists %s (%s)",
                self._tablename,
                column_defs,
            )
            if is_future(cur):
                yield cur

    def name(self):
        return self.schema["title"]

    @gen.coroutine
    def exists(self, id_):
        with (yield self.cursor(self.connection)) as cursor:
            cur = dbapiext.execute_f(
                cursor, "select 1 from %s where id = %X", self._tablename, id_
            )
            if is_future(cur):
                cur = yield cur
            return cur.fetchone() is not None

    @gen.coroutine
    def create(self, attributes):
        with (yield self.cursor(self.connection, transaction=True)) as cursor:
            cur = dbapiext.execute_f(
                cursor,
                "insert into %s (%s) values (%X)",
                self._tablename,
                list(attributes.keys()),
                list(attributes.values()),
            )
            if is_future(cur):
                cur = yield cur
        with (yield self.cursor(self.connection)) as cursor:
            # XXX assuming id is monotonically increasing
            cur = dbapiext.execute_f(
                cursor,
                "select %s from %s order by id desc limit 1",
                self.columns + ["id"],
                self._tablename,
            )
            if is_future(cur):
                cur = yield cur
            return DBAPI2Resource.ResourceObject(self, cur.fetchone())

    @gen.coroutine
    def read(self, id_):
        with (yield self.cursor(self.connection)) as cursor:
            cur = dbapiext.execute_f(
                cursor,
                "select %s from %s where id = %X",
                self.columns + ["id"],
                self._tablename,
                id_,
            )
            if is_future(cur):
                cur = yield cur
            row = cur.fetchone()
            if not row:
                return None
            return DBAPI2Resource.ResourceObject(self, row)

    @gen.coroutine
    def update(self, id_, attributes):
        with (yield self.cursor(self.connection, transaction=True)) as cursor:
            cur = dbapiext.execute_f(
                cursor,
                "update %s set %X where id = %X",
                self._tablename,
                attributes,
                id_,
            )
            if is_future(cur):
                cur = yield cur
        with (yield self.cursor(self.connection)) as cursor:
            cur = dbapiext.execute_f(
                cursor,
                "select %s from %s where id = %X",
                self.columns + ["id"],
                self._tablename,
                id_,
            )
            if is_future(cur):
                cur = yield cur
            return DBAPI2Resource.ResourceObject(self, cur.fetchone())

    @gen.coroutine
    def delete(self, id_):
        with (yield self.cursor(self.connection, transaction=True)) as cursor:
            cur = dbapiext.execute_f(
                cursor, "delete from %s where id = %X", self._tablename, id_
            )
            if is_future(cur):
                cur = yield cur
            return cur.rowcount

    @gen.coroutine
    def list_(self, limit=0, page=0):
        with (yield self.cursor(self.connection)) as cursor:
            if limit > 0:
                start = abs(page) * limit
                cur = dbapiext.execute_f(
                    cursor,
                    "select %s from %s limit %d offset %d",
                    self.columns + ["id"],
                    self._tablename,
                    limit,
                    start,
                )
            else:
                cur = dbapiext.execute_f(
                    cursor,
                    "select %s from %s",
                    self.columns + ["id"],
                    self._tablename,
                )
            if is_future(cur):
                cur = yield cur
            rows = cur.fetchall()
            return [DBAPI2Resource.ResourceObject(self, row) for row in rows]

    @gen.coroutine
    def list_count(self):
        with (yield self.cursor(self.connection)) as cursor:
            cur = dbapiext.execute_f(
                cursor, "select count(1) from %s", self._tablename
            )
            if is_future(cur):
                cur = yield cur
            rows = cur.fetchone()
            return rows[0]
