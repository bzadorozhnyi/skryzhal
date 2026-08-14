import uuid

from jobs.endpoints.v1.routes.router import router
from jobs.endpoints.v1.schemas.response.job import JobOut
from jobs.use_cases.get_job import GetJobUseCaseDep


@router.get("/{job_id}", response_model=JobOut)
async def get_job(job_id: uuid.UUID, use_case: GetJobUseCaseDep) -> JobOut:
    dto = await use_case.execute(job_id=job_id)
    return JobOut.from_dto(dto)
