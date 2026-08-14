import uuid

from fastapi import Response, status

from jobs.endpoints.v1.routes.router import router
from jobs.endpoints.v1.schemas.request.job import CreateJobIn
from jobs.endpoints.v1.schemas.response.job import JobOut
from jobs.use_cases.create_job import CreateJobUseCaseDep


@router.put("/{job_id}", response_model=JobOut)
async def create_job(
    job_id: uuid.UUID,
    data: CreateJobIn,
    use_case: CreateJobUseCaseDep,
    response: Response,
) -> JobOut:
    result = await use_case.execute(job_id=job_id, data=data)
    response.status_code = (
        status.HTTP_201_CREATED if result.created else status.HTTP_200_OK
    )
    return JobOut.from_dto(result.job)
