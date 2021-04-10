# encoding: utf-8

# This file contains commonly used parts of external libraries. The idea is
# to help in removing helpers from being used as a dependency by many files
# but at the same time making it easy to change for example the json lib
# used.
#
# NOTE:  This file is specificaly created for
# from ckan.common import x, y, z to be allowed

from collections import MutableMapping

import flask
import six
from werkzeug.datastructures import ImmutableMultiDict

from werkzeug.local import Local, LocalProxy

from flask_babel import (gettext as flask_ugettext,
                         ngettext as flask_ungettext)

import simplejson as json
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple, TypeVar, Union, overload

if six.PY2:
    import pylons  # type: ignore
    from pylons.i18n import (ugettext as pylons_ugettext,  # type: ignore
                             ungettext as pylons_ungettext)
    from pylons import response  # type: ignore

current_app = flask.current_app


def is_flask_request() -> bool:
    u'''
    A centralized way to determine whether we are in the context of a
    request being served by Flask or Pylons
    '''
    if six.PY3:
        return True
    try:
        pylons.request.environ  # type: ignore
        pylons_request_available = True
    except TypeError:
        pylons_request_available = False

    return (flask.request and
            (flask.request.environ.get(u'ckan.app') == u'flask_app' or
             not pylons_request_available))


def streaming_response(
        data: Iterable[Any],
        mimetype: str=u'application/octet-stream',
        with_context: bool=False) -> flask.Response:
    iter_data = iter(data)
    if is_flask_request():
        # Removal of context variables for pylon's app is prevented
        # inside `pylons_app.py`. It would be better to decide on the fly
        # whether we need to preserve context, but it won't affect performance
        # in any visible way and we are going to get rid of pylons anyway.
        # Flask allows to do this in easy way.
        if with_context:
            iter_data = flask.stream_with_context(iter_data)
        resp = flask.Response(iter_data, mimetype=mimetype)
    else:
        response.app_iter = iter_data  # type: ignore
        resp = response.headers['Content-type'] = mimetype  # type: ignore
        assert False
    return resp


def ugettext(*args, **kwargs) -> str:
    return flask_ugettext(*args, **kwargs)


_ = ugettext


def ungettext(*args, **kwargs) -> str:
    if is_flask_request():
        return flask_ungettext(*args, **kwargs)
    else:
        return pylons_ungettext(*args, **kwargs)  # type: ignore


class CKANConfig(MutableMapping):
    u'''Main CKAN configuration object

    This is a dict-like object that also proxies any changes to the
    Flask and Pylons configuration objects.

    The actual `config` instance in this module is initialized in the
    `load_environment` method with the values of the ini file or env vars.

    '''
    store: Dict[str, Any]

    def __init__(self, *args, **kwargs):
        self.store = dict()
        self.update(dict(*args, **kwargs))

    def __getitem__(self, key):
        return self.store[key]

    def __iter__(self):
        return iter(self.store)

    def __len__(self):
        return len(self.store)

    def __repr__(self):
        return self.store.__repr__()

    def copy(self) -> Dict[str, Any]:
        return self.store.copy()

    def clear(self) -> None:
        self.store.clear()

        try:
            flask.current_app.config.clear()
        except RuntimeError:
            pass

        if six.PY2:
            try:
                pylons.config.clear()
                # Pylons set this default itself
                pylons.config[u'lang'] = None
            except TypeError:
                pass

    def __setitem__(self, key: str, value: Any):
        self.store[key] = value
        try:
            flask.current_app.config[key] = value
        except RuntimeError:
            pass

        if six.PY2:
            try:
                pylons.config[key] = value
            except TypeError:
                pass

    def __delitem__(self, key: str):
        del self.store[key]
        try:
            del flask.current_app.config[key]
        except RuntimeError:
            pass

        if six.PY2:
            try:
                del pylons.config[key]
            except TypeError:
                pass


def _get_request() -> flask.Request:
    if is_flask_request():
        return flask.request
    else:
        return pylons.request


class CKANRequest(LocalProxy):
    u'''Common request object

    This is just a wrapper around LocalProxy so we can handle some special
    cases for backwards compatibility.

    LocalProxy will forward to Flask or Pylons own request objects depending
    on the output of `_get_request` (which essentially calls
    `is_flask_request`) and at the same time provide all objects methods to be
    able to interact with them transparently.
    '''

    @property
    def params(self) -> ImmutableMultiDict:
        u''' Special case as Pylons' request.params is used all over the place.
        All new code meant to be run just in Flask (eg views) should always
        use request.args
        '''
        try:
            return super(CKANRequest, self).params
        except AttributeError:
            return self.args


def _get_c() -> Any:
    if is_flask_request():
        return flask.g
    else:
        return pylons.c


def _get_session() -> Any:
    if is_flask_request():
        return flask.session
    else:
        return pylons.session


local = Local()

# This a proxy to the bounded config object
local(u'config')

# Thread-local safe objects
config = local.config = CKANConfig()

# Proxies to already thread-local safe objects
request = CKANRequest(_get_request)
# Provide a `c`  alias for `g` for backwards compatibility
g: Any
c: Any
g = c = LocalProxy(_get_c)

session: Any
session = LocalProxy(_get_session)

truthy = frozenset([u'true', u'yes', u'on', u'y', u't', u'1'])
falsy = frozenset([u'false', u'no', u'off', u'n', u'f', u'0'])


def asbool(obj: Any) -> bool:
    if isinstance(obj, six.string_types):
        obj = obj.strip().lower()
        if obj in truthy:
            return True
        elif obj in falsy:
            return False
        else:
            raise ValueError(u"String is not true/false: {}".format(obj))
    return bool(obj)


def asint(obj: Any) -> int:
    try:
        return int(obj)
    except (TypeError, ValueError):
        raise ValueError(u"Bad integer value: {}".format(obj))


T = TypeVar('T')
SequenceT = TypeVar('SequenceT', list, tuple)

@overload
def aslist(obj: str, sep: Optional[str]=None, strip: bool=True) -> List[str]: ...


@overload
def aslist(obj: List[T], sep: Optional[str]=None, strip: bool=True) -> List[T]: ...


@overload
def aslist(obj: Tuple[T], sep: Optional[str]=None, strip: bool=True) -> Tuple[T]: ...


@overload
def aslist(obj: SequenceT, sep: Optional[str]=None, strip: bool=True) -> SequenceT: ...


def aslist(obj, sep=None, strip=True):
    if isinstance(obj, six.string_types):
        lst = obj.split(sep)
        if strip:
            lst = [v.strip() for v in lst]
        return lst
    elif isinstance(obj, (list, tuple)):
        return obj
    elif obj is None:
        return []
    else:
        return [obj]
