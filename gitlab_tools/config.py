import getpass
from urllib.parse import urlparse

import gitlab
import gitlab.v4
import gitlab.v4.objects
import keyring

import logging
import structlog
import structlog.processors

from typing import List

import string

import hashlib
import base64
from random import SystemRandom

from .uiclient import uiclient
from .logutil import renderers

logger: structlog.BoundLogger = structlog.getLogger()


def log_levels() -> List[str]:
    """return a list of supported log levels"""
    return [l.lower() for l in logging._nameToLevel.keys()]


def configure_logging(log_level: str) -> None:
    """configure logging globally"""
    level_type = logging._nameToLevel.get(log_level.upper(), None)
    if level_type is None:
        raise Exception("invalid log level type: {}".format(log_level))

    logging.basicConfig(level=level_type)

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            renderers.ColorKeyValueRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


class Secret(object):
    """This type is masked in logs and uniquely salts on initialization."""

    SALT_LENGTH = 10
    SALT_SPACE = string.ascii_lowercase + string.digits
    MASK = "**MASKED**"

    def __hash__(self):
        return self._repr

    def __repr__(self):
        return "Secret:salt={} hash={}".format(self._salt, self._repr)

    def __str__(self):
        return self.MASK

    def unmasked(self) -> str:
        """return the real value"""
        return self._value

    def __init__(self, value):
        """initializes a secret value and sets its representatio nto a sha256 hash"""
        self._salt = "".join(
            [SystemRandom().choice(self.SALT_SPACE) for _ in range(self.SALT_LENGTH)]
        )
        self._value = value

        m = hashlib.sha256()
        m.update(self._salt.encode("utf8"))
        m.update(self._value.encode("utf8"))

        self._repr = base64.encodebytes(m.digest()).decode("utf-8")


class Config(object):
    DEFAULT_USER = "__default"
    DEFAULT_SERVER = "https://gitlab.com"

    ssl_verify = True
    gitlab_server = DEFAULT_SERVER

    def get_service_name(self) -> str:
        u = urlparse(self.gitlab_server)
        service_name = "{}:api".format(u.netloc)
        self.logger = self.logger.bind(service_name=service_name)
        self.logger.debug("Got service name.")
        return service_name

    def get_gitlab_client(self) -> gitlab.Gitlab:
        """get a gitlab client based on the current config"""
        self.logger.debug("Setting up gitlab client")
        gl = gitlab.Gitlab(
            self.gitlab_server, private_token=self.token.unmasked(), ssl_verify=self.ssl_verify
        )

        self.logger.debug("Authenticating to gitlab...")
        gl.auth()
        try:
            user_id = gl.user.get_id()
            self.logger = self.logger.bind(gitlab_userid=user_id)
            self.logger.info("Authenticated as user")
        except Exception as e:
            raise e
        return gl

    def _get_user(self, user) -> str:
        """get or set the user (used when initializing the object)"""
        if user is None:
            user = keyring.get_password(self.get_service_name(), self.DEFAULT_USER)
            while user is None or user == "":
                if not self.allow_prompting:
                    raise Exception(
                        "No Gitlab user specified or found in password backend for {}".format(
                            self.gitlab_server
                        )
                    )

                new_default_user = input(
                    "Enter a Gitlab username to login as by default for {}: ".format(
                        self.gitlab_server
                    )
                )
                keyring.set_password(self.get_service_name(), self.DEFAULT_USER, new_default_user)
                user = keyring.get_password(self.get_service_name(), self.DEFAULT_USER)
        self.logger = self.logger.bind(user=user)
        self.logger.debug("Local user found")
        return user

    def _get_token(self) -> Secret:
        """refresh the gitlab token"""
        gitlab_token = keyring.get_password(self.get_service_name(), self.user)
        while gitlab_token is None or gitlab_token == "":
            new_password = getpass.getpass("Enter a private token for user {}: ".format(self.user))
            keyring.set_password(self.get_service_name(), self.user, new_password)
            gitlab_token = keyring.get_password(self.get_service_name(), self.user)
        token = Secret(gitlab_token)
        self.logger.debug("Gitlab Token found", masked_gitlab_token=token.__repr__())
        return token

    @property
    def otp_secret(self) -> Secret:
        """get the user password"""
        service_name = uiclient.OTP_SERVICE_TEMPLATE.format(url=urlparse(self.gitlab_server).netloc)
        otp_secret = keyring.get_password(service_name, self.user)
        if otp_secret is None or otp_secret == "":
            new_otp_secret = getpass.getpass(
                "Enter a base32 OTP secret for the user {} on {}: ".format(
                    self.user, self.gitlab_server
                )
            )
            keyring.set_password(service_name, self.user, new_otp_secret)
            otp_secret = keyring.get_password(service_name, self.user)
        return Secret(otp_secret)

    @property
    def user_password(self) -> Secret:
        """get the OTP secret from the user"""
        service_name = "{}:user_password".format(urlparse(self.gitlab_server).netloc)
        user_password = keyring.get_password(service_name, self.user)
        if user_password is None or user_password == "":
            new_otp_secret = getpass.getpass(
                "Enter the login password for {} on {}: ".format(self.user, self.gitlab_server)
            )
            keyring.set_password(service_name, self.user, new_otp_secret)
            otp_secret = keyring.get_password(service_name, self.user)
        return Secret(user_password)

    @property
    def client(self) -> gitlab.Gitlab:
        if self._gitlab_client is None:
            self._gitlab_client = self.get_gitlab_client()
        return self._gitlab_client

    def __init__(
        self,
        gitlab_server=DEFAULT_SERVER,
        user=DEFAULT_USER,
        ssl_verify=True,
        allow_prompting=False,
    ):
        """
        object initialization
        :param gitlab_server: gitlab server url
        :param allow_prompting: allow prompting on the console
        :param user: user to login as
        """
        self.logger = logger
        self.gitlab_server = gitlab_server
        self.allow_prompting = allow_prompting
        self.user = self._get_user(user)
        self.token = self._get_token()
        self.ssl_verify = ssl_verify

        self._gitlab_client = None
        # ctxstack contains the appended results of interstitial commands
