import json
import pprint
import re
import threading
import time
import uuid

import requests
import requests.adapters

from .constant import (LOGIN_PATH, DEVICES_PATH)

# include token and session details
class BHyveBackEnd(object):

    def __init__(self, bhyve):

        self._bhyve = bhyve
        self._lock = threading.Condition()
        self._req_lock = threading.Lock()

        self._requests = {}
        self._callbacks = {}

        self._token = None

        # login
        self._session = None
        self._logged_in = self._login()
        if not self._logged_in:
            self._bhyve.warning('failed to log in')
            return


    def _request(self, path, method='GET', params=None, headers=None, stream=False, timeout=None):
        if params is None:
            params = {}
        if headers is None:
            headers = {}
        if timeout is None:
            timeout = self._bhyve.cfg.request_timeout
        try:
            with self._req_lock:
                url = self._bhyve.cfg.host + path
                self._bhyve.debug('starting request=' + str(url))
                # self._bhyve.debug('starting request=' + str(params))
                # self._bhyve.debug('starting request=' + str(headers))
                if method == 'GET':
                    r = self._session.get(url, params=params, headers=headers, stream=stream, timeout=timeout)
                    if stream is True:
                        return r
                elif method == 'PUT':
                    r = self._session.put(url, json=params, headers=headers, timeout=timeout)
                elif method == 'POST':
                    r = self._session.post(url, json=params, headers=headers, timeout=timeout)
        except Exception as e:
            self._bhyve.warning('request-error={}'.format(type(e).__name__))
            return None

        self._bhyve.debug('finish request=' + str(r.status_code))
        if r.status_code != 200:
            return None

        body = r.json()
        # self._bhyve.debug(pprint.pformat(body, indent=2))

        return body

    # login and set up session
    def _login(self):

        # attempt login
        self._session = requests.Session()
        body = self.post(LOGIN_PATH, { 'session': {'email': self._bhyve.cfg.username, 'password': self._bhyve.cfg.password} })
        if body is None:
            self._bhyve.debug('login failed')
            return False

        # save new login information
        self._token = body['orbit_session_token']
        self._user_id = body['user_id']

        headers = {
            'Accept': 'application/json, text/plain, */*',
            'Host': re.sub('https?://', '', self._bhyve.cfg.host),
            'Content-Type': 'application/json; charset=utf-8;',
            'Referer': self._bhyve.cfg.host,
            'Orbit-Session-Token': self._token
        }
        headers['User-Agent'] = ('Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) '
                                 'Chrome/72.0.3626.81 Safari/537.36')

        self._session.headers.update(headers)
        return True

    def is_connected(self):
        return self._logged_in

    def get(self, path, params=None, headers=None, stream=False, timeout=None):
        return self._request(path, 'GET', params, headers, stream, timeout)

    def put(self, path, params=None, headers=None, timeout=None):
        return self._request(path, 'PUT', params, headers, False, timeout)

    def post(self, path, params=None, headers=None, timeout=None):
        return self._request(path, 'POST', params, headers, False, timeout)

    @property
    def session(self):
        return self._session

    def devices(self):
        return self.get(DEVICES_PATH + "?t={}".format(time.time()))
