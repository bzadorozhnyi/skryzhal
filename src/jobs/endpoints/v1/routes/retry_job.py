import uuid

from jobs.endpoints.v1.routes.router import router
from jobs.endpoints.v1.schemas.response.job import JobOut
from jobs.use_cases.retry_job import RetryJobUseCaseDep


@router.post("/{job_id}/retry", response_model=JobOut)
async def retry_job(job_id: uuid.UUID, use_case: RetryJobUseCaseDep) -> JobOut:
    dto = await use_case.execute(job_id=job_id)
    return JobOut.from_dto(dto)
