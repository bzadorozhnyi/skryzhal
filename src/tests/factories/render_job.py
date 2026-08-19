import uuid

import factory
import pytest

from jobs.models.render_job import JobStatus, RenderJob
from tests.helpers.factory import AsyncFactory


@pytest.fixture
def render_job_factory(db_session, template_factory):
    class RenderJobFactory(factory.alchemy.SQLAlchemyModelFactory):
        class Meta:
            model = RenderJob
            sqlalchemy_session = db_session.sync_session
            sqlalchemy_session_persistence = "flush"
            exclude = ("template",)

        id = factory.LazyFunction(uuid.uuid4)
        # Override via `template=`, not `template_id=` — that's what lets
        # SubFactory recognize the override and skip creating a new one.
        template = factory.SubFactory(template_factory.factory_class)
        template_id = factory.LazyAttribute(lambda o: o.template.id)
        input_data = factory.LazyFunction(dict)
        status = JobStatus.PENDING
        attempt_count = 0

    return AsyncFactory(factory_class=RenderJobFactory, session=db_session)
