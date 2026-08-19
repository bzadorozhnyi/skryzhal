import hashlib
import uuid

import factory
import pytest

from templates.models.template import Template
from tests.helpers.factory import AsyncFactory


@pytest.fixture
def template_factory(db_session):
    class TemplateFactory(factory.alchemy.SQLAlchemyModelFactory):
        class Meta:
            model = Template
            sqlalchemy_session = db_session.sync_session
            sqlalchemy_session_persistence = "flush"

        id = factory.LazyFunction(uuid.uuid4)
        slug = factory.Sequence(lambda n: f"template-{n}")
        name = factory.Faker("word")
        version = 1
        s3_key = factory.LazyAttribute(lambda o: f"templates/{o.slug}/v{o.version}.typ")
        checksum = factory.LazyFunction(
            lambda: hashlib.sha256(uuid.uuid4().bytes).hexdigest()
        )

    return AsyncFactory(factory_class=TemplateFactory, session=db_session)
