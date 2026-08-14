import asyncio
import json


class TypstCompilationError(Exception):
    def __init__(self, stderr: str):
        self.stderr = stderr
        super().__init__(stderr)


async def compile_typst(*, template: bytes, input_data: dict) -> bytes:
    process = await asyncio.create_subprocess_exec(
        "typst",
        "compile",
        "-",
        "-",
        "--input",
        f"data={json.dumps(input_data)}",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate(input=template)

    if process.returncode != 0:
        raise TypstCompilationError(stderr.decode())

    return stdout
