from fastapi import status

from templates.endpoints.v1.routes.router import router
from templates.endpoints.v1.schemas.request.upload_url import UploadUrlIn
from templates.endpoints.v1.schemas.response.upload_url import UploadUrlOut
from templates.use_cases.create_upload_url import CreateUploadUrlUseCaseDep


@router.post(
    "/upload-url", response_model=UploadUrlOut, status_code=status.HTTP_201_CREATED
)
async def create_upload_url(
    data: UploadUrlIn, use_case: CreateUploadUrlUseCaseDep
) -> UploadUrlOut:
    dto = await use_case.execute(data=data)
    return UploadUrlOut.from_dto(dto)
