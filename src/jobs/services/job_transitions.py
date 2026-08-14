from core.exceptions import ConflictException
from jobs.models.render_job import JobStatus, RenderJob

ALLOWED_TRANSITIONS: dict[JobStatus, set[JobStatus]] = {
    JobStatus.PENDING: {JobStatus.PROCESSING},
    JobStatus.PROCESSING: {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.PENDING},
    JobStatus.FAILED: {JobStatus.PENDING},
    JobStatus.COMPLETED: set(),
}


def transition(*, job: RenderJob, status: JobStatus) -> None:
    if status not in ALLOWED_TRANSITIONS.get(job.status, set()):
        raise ConflictException(
            f"Cannot transition job {job.id} from {job.status} to {status}"
        )
    job.status = status
