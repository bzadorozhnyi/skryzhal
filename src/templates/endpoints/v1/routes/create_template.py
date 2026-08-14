from fastapi import status

from templates.endpoints.v1.routes.router import router
from templates.endpoints.v1.schemas.request.template import CreateTemplateIn
from templates.endpoints.v1.schemas.response.template import TemplateOut
from templates.use_cases.create_template import CreateTemplateUseCaseDep


@router.post("", response_model=TemplateOut, status_code=status.HTTP_201_CREATED)
async def create_template(
    data: CreateTemplateIn, use_case: CreateTemplateUseCaseDep
) -> TemplateOut:
    dto = await use_case.execute(data=data)
    return TemplateOut.from_dto(dto)
