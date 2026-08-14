from fastapi import status

from jobs.endpoints.v1.routes.router import router
from jobs.endpoints.v1.schemas.request.job import CreateJobIn
from jobs.endpoints.v1.schemas.response.job import JobOut
from jobs.use_cases.create_job import CreateJobUseCaseDep


@router.post("", response_model=JobOut, status_code=status.HTTP_201_CREATED)
async def create_job(data: CreateJobIn, use_case: CreateJobUseCaseDep) -> JobOut:
    return await use_case.execute(data=data)
