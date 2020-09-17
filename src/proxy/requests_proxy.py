# -*- encoding=utf-8 -*-
import logging
import requests
from requests.auth import HTTPBasicAuth
try:
    from urllib import urlencode
except ImportError:
    from urllib.parse import urlencode

logger = logging.getLogger("common")


def do_requests(method, url, querystring=None, body=None, auth=None, timeout=30, obj=None):
    """
    http request
    :param method: http method
    :param url: http[s] schema
    :param querystring: dict
    :param body: json
    :param auth: dict, basic auth with user and password
    :param timeout: second
    :param obj: callback object, support list/dict/object
    :return:
    """
    try:
        logger.debug("http requests, {} {} {}".format(method, url, timeout))
        logger.debug("querystring: {}".format(querystring))
        logger.debug("body: {}".format(body))

        if method.lower() not in ["get", "post", "put", "delete"]:
            return -1

        if querystring:
            url = "{}?{}".format(url, urlencode(querystring))

        func = getattr(requests, method.lower())
        if body:
            if auth:
                rs = func(url, json=body, timeout=timeout, auth=HTTPBasicAuth(auth["user"], auth["password"]))
            else:
                rs = func(url, json=body, timeout=timeout)
        else:
            if auth:
                rs = func(url, timeout=timeout, auth=HTTPBasicAuth(auth["user"], auth["password"]))
            else:
                rs = func(url, timeout=timeout)

        logger.debug("status_code {}".format(rs.status_code))

        if rs.status_code not in [requests.codes.ok, requests.codes.created, requests.codes.no_content]:
            return 1

        # return response
        if obj is not None:
            if isinstance(obj, list):
                obj.extend(rs.json())
            elif isinstance(obj, dict):
                obj.update(rs.json())
            elif callable(obj):
                obj(rs)
            elif hasattr(obj, "cb"):
                getattr(obj, "cb")(rs.json())

        return 0
    except requests.exceptions.SSLError as e:
        logger.warning("requests {} ssl exception, {}".format(url, e))
        return -2
    except requests.exceptions.Timeout as e:
        logger.warning("requests timeout")
        return 2
    except Exception as e:
        logger.warning("requests exception, {}".format(e))
        return 3