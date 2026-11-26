"""The REST client of the Analytics service: its reports with a JWT.

    client = AnalyticsClient()
    client.get("/api/reports/summary/", {"from": "2026-11-01", "to": "2026-11-30"})
    -> the JSON of the answer (dict)

The account: ANALYTICS_API_USERNAME / _PASSWORD ("bookstore-service" in
the group Services of Analytics). Its access token lives 15 minutes in
Analytics; it is kept in the cache (Redis) for 14, so all the gunicorn
workers and processes share one token instead of logging in on every page.

Errors, all of them AnalyticsError:
    AnalyticsNotConfigured  no ANALYTICS_API_URL / password: nothing called
    AnalyticsUnavailable    no connection, a timeout, 5xx, 429, not JSON:
                            "try later". Logged as WARNING. Also remembered
                            for ANALYTICS_DOWN_TIMEOUT seconds: the next
                            calls fail at once instead of waiting for the
                            timeouts again (a simple circuit breaker)
    AnalyticsRefused        the login or the rights are wrong (401 / 403
                            after a new token), or Analytics refused the
                            request (400): a mistake of the settings or of
                            this code, not "later". Logged as ERROR, so
                            Sentry shows it

The password and the token never go to the logs.
"""

import logging

import requests
from django.conf import settings
from django.core.cache import cache
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

logger = logging.getLogger(__name__)  # "analytics.client"

TOKEN_PATH = "/api/token/"
TOKEN_CACHE_KEY = "analytics:token"
# 1 minute less than the access token of Analytics lives (15 minutes): a
# token taken from the cache always has some time left
TOKEN_CACHE_TIMEOUT = 14 * 60
DOWN_CACHE_KEY = "analytics:down"


class AnalyticsError(Exception):
    """Any problem with Analytics; the page shows a message instead of the numbers."""


class AnalyticsNotConfigured(AnalyticsError):
    pass


class AnalyticsUnavailable(AnalyticsError):
    pass


class AnalyticsRefused(AnalyticsError):
    pass


class AnalyticsClient:
    def __init__(self, base_url=None, username=None, password=None, session=None):
        self.base_url = (base_url if base_url is not None else settings.ANALYTICS_API_URL).rstrip(
            "/"
        )
        self.username = username if username is not None else settings.ANALYTICS_API_USERNAME
        self.password = password if password is not None else settings.ANALYTICS_API_PASSWORD
        self.session = session or self.make_session()

    @staticmethod
    def make_session():
        # One retry of a 502 / 503 / 504 (Analytics restarting behind its
        # nginx), half a second later. Not more: a manager waits for it
        retry = Retry(
            total=1,
            backoff_factor=0.5,
            status_forcelist=(502, 503, 504),
            # POST too: getting a token changes nothing in Analytics
            allowed_methods=frozenset({"GET", "POST"}),
            # Give the 5xx answer back instead of raising: one place below
            # decides what an error status means
            raise_on_status=False,
        )
        session = requests.Session()
        session.mount("http://", HTTPAdapter(max_retries=retry))
        session.mount("https://", HTTPAdapter(max_retries=retry))
        return session

    @property
    def configured(self):
        return bool(self.base_url and self.username and self.password)

    # --- Public ---------------------------------------------------------------

    def get(self, path, params=None):
        """GET a report: the JSON answer, or an AnalyticsError."""
        if not self.configured:
            raise AnalyticsNotConfigured(
                "Set ANALYTICS_API_URL, ANALYTICS_API_USERNAME and ANALYTICS_API_PASSWORD"
            )
        if cache.get(DOWN_CACHE_KEY):
            raise AnalyticsUnavailable("Analytics failed a moment ago, not called again yet")
        try:
            return self._get(path, params or {})
        except AnalyticsUnavailable:
            cache.set(DOWN_CACHE_KEY, True, settings.ANALYTICS_DOWN_TIMEOUT)
            raise

    # --- Inside ---------------------------------------------------------------

    def _get(self, path, params):
        response = self._request("GET", path, params=params, headers=self._auth(self.token()))
        if response.status_code == 401:
            # The token expired earlier than the cache thought (Analytics
            # restarted with a new key, the clocks differ): one new token
            cache.delete(TOKEN_CACHE_KEY)
            response = self._request("GET", path, params=params, headers=self._auth(self.token()))
        self._check(response, path)
        return self._json(response, path)

    def token(self):
        token = cache.get(TOKEN_CACHE_KEY)
        if token:
            return token
        response = self._request(
            "POST", TOKEN_PATH, json={"username": self.username, "password": self.password}
        )
        if response.status_code in (400, 401):
            # Not the answer's text: it could repeat what was sent
            logger.error(
                "Analytics refused the login of %r (HTTP %s): check ANALYTICS_API_USERNAME "
                "and ANALYTICS_API_PASSWORD",
                self.username,
                response.status_code,
            )
            raise AnalyticsRefused(f"Login refused (HTTP {response.status_code})")
        self._check(response, TOKEN_PATH)
        token = self._json(response, TOKEN_PATH).get("access")
        if not token:
            logger.warning("Analytics: the token answer has no access token")
            raise AnalyticsUnavailable("No access token in the answer")
        cache.set(TOKEN_CACHE_KEY, token, TOKEN_CACHE_TIMEOUT)
        return token

    def _request(self, method, path, **kwargs):
        url = f"{self.base_url}{path}"
        try:
            return self.session.request(
                method, url, timeout=settings.ANALYTICS_API_TIMEOUT, **kwargs
            )
        except requests.RequestException as error:
            # No connection, DNS, a timeout, too many retries
            logger.warning("Analytics is not reachable: %s %s: %r", method, url, error)
            raise AnalyticsUnavailable(str(error)) from error

    def _check(self, response, path):
        status = response.status_code
        if status == 200:
            return
        if status >= 500 or status == 429:
            logger.warning("Analytics answered HTTP %s to %s", status, path)
            raise AnalyticsUnavailable(f"HTTP {status}")
        if status in (401, 403):
            logger.error(
                "Analytics refused %s to %r (HTTP %s): the account needs the group Services "
                "there",
                path,
                self.username,
                status,
            )
        else:
            # 400 (a wrong period: a bug here), 404 (a wrong address)
            logger.error("Analytics answered HTTP %s to %s: %s", status, path, response.text[:300])
        raise AnalyticsRefused(f"HTTP {status}")

    @staticmethod
    def _json(response, path):
        try:
            data = response.json()
        except ValueError as error:
            logger.warning("Analytics answered %s with something that is not JSON", path)
            raise AnalyticsUnavailable("Not JSON") from error
        if not isinstance(data, dict):
            logger.warning("Analytics answered %s with JSON that is not an object", path)
            raise AnalyticsUnavailable("Not a JSON object")
        return data

    @staticmethod
    def _auth(token):
        return {"Authorization": f"Bearer {token}"}
