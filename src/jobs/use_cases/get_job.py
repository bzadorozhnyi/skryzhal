import uuid
from typing import Annotated

from fastapi import Depends

from core.exceptions import NotFoundException
from jobs.dto.job import JobDTO
from jobs.models.render_job import JobStatus
from jobs.repositories.job import JobRepository, JobRepositoryDep
from jobs.repositories.storage import JobStorageRepository, JobStorageRepositoryDep


class GetJobUseCase:
    def __init__(
        self, *, job_repository: JobRepository, job_storage: JobStorageRepository
    ):
        self.job_repository = job_repository
        self.job_storage = job_storage

    async def execute(self, *, job_id: uuid.UUID) -> JobDTO:
        job = await self.job_repository.get_by_id(job_id=job_id)
        if job is None:
            raise NotFoundException(f"Job {job_id} not found")

        get_url = None
        if job.status == JobStatus.COMPLETED and job.result_s3_key:
            get_url = await self.job_storage.generate_get_url(key=job.result_s3_key)

        return JobDTO(
            id=job.id,
            template_id=job.template_id,
            status=job.status,
            get_url=get_url,
            error_message=job.error_message,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )


def get_get_job_use_case(
    job_repository: JobRepositoryDep,
    job_storage: JobStorageRepositoryDep,
) -> GetJobUseCase:
    return GetJobUseCase(job_repository=job_repository, job_storage=job_storage)


GetJobUseCaseDep = Annotated[GetJobUseCase, Depends(get_get_job_use_case)]
