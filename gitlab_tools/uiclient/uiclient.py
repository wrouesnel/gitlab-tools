"""Implement a requests based client to drive the Gitlab UI"""

from urllib.parse import urlparse

import structlog
import requests
import pyotp
from bs4 import BeautifulSoup

BEAUTIFULSOUP_PARSER = "lxml"

logger: structlog.BoundLogger = structlog.getLogger()

# Use this to store OTP secrets in keyring
OTP_SERVICE_TEMPLATE = "{url}:otp"


def gitlab_get_csrf(soup):
    """Accept a beautiful soup item and extract the CSRF meta tags"""
    csrf_param = None
    csrf_token = None
    for meta_tag in soup.find_all("meta"):
        if {"name", "content"}.issubset(meta_tag.attrs.keys()):
            if meta_tag.attrs["name"] == "csrf-param":
                csrf_param = meta_tag.attrs["content"]
            if meta_tag.attrs["name"] == "csrf-token":
                csrf_token = meta_tag.attrs["content"]

    if csrf_param is not None and csrf_token is not None:
        logger.bind(csrf_param=csrf_param, csrf_token=csrf_token).debug("Got new CSRF tokens")
        return {csrf_param: csrf_token}
    else:
        logger.debug("No CSRF tokens found for request")
        return {}


class ErrorGitlabLoginFailed(Exception):
    pass


class GitlabUIClient(object):
    """wraps the functions needed to navigate the gitlab website with requests"""

    def __init__(
        self,
        server_url: str,
        username: str,
        password: str,
        otp_secret: str,
        session: requests.Session = None,
    ):
        self.base_url = server_url

        self.session = session if session is not None else requests.Session()
        self.username = username
        self.password = password
        self.otp = pyotp.TOTP(otp_secret)

        self._log = logger.bind(server_url=self.base_url, username=self.username)
        # Store CSRF data
        self._csrf_data = {}

    def _do_login(self):
        """Do the Gitlab UI login flow"""
        r = self.session.get("https://gitlab.com/users/sign_in")
        soup = BeautifulSoup(r.text, BEAUTIFULSOUP_PARSER)
        self._csrf_data = gitlab_get_csrf(soup)
        login_data = {
            "user[login]": self.username,
            "user[password]": self.password,
            "user[remember_me]": 0,
            "utf8": "✓",
        }
        login_data.update(self._csrf_data)

        self._log.debug("Doing username and password login")
        r = self.session.post(
            "https://gitlab.com/users/sign_in", data=login_data, allow_redirects=False
        )
        if r.status_code == 302:
            self._log.debug("Login succeeded without OTP")
            return
        self._log.debug("Login requires OTP")
        if self.otp is None:
            raise ErrorGitlabLoginFailed("Gitlab login required OTP but OTP token not supplied.")

        soup = BeautifulSoup(r.text, BEAUTIFULSOUP_PARSER)
        self._csrf_data = gitlab_get_csrf(soup)
        otp_data = {"user[otp_attempt]": self.otp.now(), "user[remember_me]": 0, "utf8": "✓"}
        otp_data.update(self._csrf_data)
        r = self.session.post(
            "https://gitlab.com/users/sign_in", data=otp_data, allow_redirects=False
        )
        if r.status_code == 302:
            self._log.debug("Login succeeded after OTP")
            return

        raise ErrorGitlabLoginFailed("Gitlab Login failed despite OTP step")

    def _check_logged_in(self, r: requests.Response) -> bool:
        """Check if the session has gone back to the login page"""
        soup = BeautifulSoup(r.text, BEAUTIFULSOUP_PARSER)

        if len(soup.find_all("div", {"class": "login-body"})) > 0:
            self._log.debug("Got log in page. You need to relogin.")
            return False

        self._log.debug("Still seem to be logged in from this response")
        return True

    def _request(self, method, url, *args, **kwargs) -> requests.Response:
        """Wraps the session.method command to handle login state management and CSRF updates"""
        log = self._log.bind(method=method, url=url)
        log.debug("Making request")
        r = self.session.request(method, url, *args, **kwargs)
        log.debug("Checking for new CSRF tokens")
        self._csrf_data = gitlab_get_csrf(BeautifulSoup(r.text))
        return r

    def _get(self, url, *args, **kwargs) -> requests.Response:
        """Wraps the session.get command to handle login state management"""
        r = self._request("GET", url, *args, **kwargs)
        while not self._check_logged_in(r):
            self._do_login()
            r = self._request("GET", url, *args, **kwargs)
        return r

    def list_repository_mirrors(self, repo_name: str):
        """List the current repository mirror configurations"""
        request_url = str(self.base_url) + "/" + repo_name + "/settings/repository"

        r = self._get(request_url)
        while not self._check_logged_in(r):
            self._do_login()
            r = self.session.get(request_url)

        soup = BeautifulSoup(r.text)

        mirror_settings = soup.find("section", {"class": "project-mirror-settings"})
        self._log.debug(mirror_settings)
