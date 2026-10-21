from os import PathLike

class OtaDumpError(Exception): ...

def extract(
    payload_file: str | PathLike[str],
    output_dir: str | PathLike[str],
    *,
    num_threads: int | None = None,
    overwrite: bool = False,
    partitions: list[str] | None = None,
    verify: bool = True,
) -> None: ...
