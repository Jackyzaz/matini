import sys
import urllib.parse
from inspect import getmembers, isclass
from typing import Sequence, Type

import beanie
import pymongo

from matini.models.llms import LLM
from matini.models.conversations import Conversation
from matini.models.assessments import Assessment


async def gather_documents() -> Sequence[Type[beanie.Document]]:
    """Returns a list of all MongoDB document models defined in `models` module."""

    class_models = getmembers(sys.modules[__name__], isclass)

    for key in [k for k in sys.modules if __name__ in k]:
        class_models.extend(getmembers(sys.modules[key], isclass))

    class_models = list(set(class_models))

    return [
        doc
        for _, doc in class_models
        if issubclass(doc, beanie.Document) and doc.__name__ != "Document"
    ]


def sanitize_mongo_uri(uri: str) -> str:
    """URL-quote the username/password part of a MongoDB URI."""
    if not uri or not ("mongodb://" in uri or "mongodb+srv://" in uri):
        return uri
    scheme, remainder = uri.split("://", 1)
    if "@" not in remainder:
        return uri
    host_db_idx = remainder.find("/")
    if host_db_idx == -1:
        host_db_idx = remainder.find("?")
    if host_db_idx != -1:
        user_host_part = remainder[:host_db_idx]
        rest = remainder[host_db_idx:]
    else:
        user_host_part = remainder
        rest = ""

    last_at = user_host_part.rfind("@")
    userinfo = user_host_part[:last_at]
    hostpart = user_host_part[last_at + 1 :]

    if ":" in userinfo:
        user, password = userinfo.split(":", 1)
        quoted_user = urllib.parse.quote_plus(urllib.parse.unquote(user))
        quoted_pass = urllib.parse.quote_plus(urllib.parse.unquote(password))
        return f"{scheme}://{quoted_user}:{quoted_pass}@{hostpart}{rest}"
    return uri


class BeanieClient:
    async def init_beanie(self, settings):
        self.settings = settings
        uri = sanitize_mongo_uri(getattr(settings, "mongodb_uri", ""))
        # tz_aware keeps BSON datetimes timezone-aware on reads, like sindhu.
        self.client = pymongo.AsyncMongoClient(uri, tz_aware=True)
        self.db = self.client.get_default_database()

        await beanie.init_beanie(
            database=self.db,
            document_models=await gather_documents(),
        )


beanie_client = BeanieClient()


async def init_beanie(app, settings):
    await beanie_client.init_beanie(settings)
