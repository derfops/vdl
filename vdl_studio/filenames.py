from __future__ import annotations


def ordered_filenames(count: int, extension: str = ".mp4") -> list[str]:
    if count < 1:
        return []
    normalized_extension = extension if extension.startswith(".") else f".{extension}"
    width = max(2, len(str(count)))
    return [f"{index:0{width}d}{normalized_extension}" for index in range(1, count + 1)]

