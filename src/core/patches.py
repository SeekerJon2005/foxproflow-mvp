# -*- coding: utf-8 -*-
# file: src/core/patches.py
from __future__ import annotations

import difflib
from typing import List, Optional

from pydantic import BaseModel, Field


class PatchEnvelope(BaseModel):
    """
    Unified diff артефакт (если DevFactory предлагает фикс).

    patch_type: фиксируем версию формата.
    target_files: явные пути файлов.
    patch: unified diff строкой.
    """

    patch_type: str = Field("unified_diff_v1", description="Patch format identifier")
    target_files: List[str] = Field(default_factory=list, description="Target file paths")
    patch: str = Field(..., description="Unified diff text")
    summary: Optional[str] = Field(None, description="Short summary of the patch")

    def to_dict(self):
        if hasattr(self, "model_dump"):  # pydantic v2
            return self.model_dump()  # type: ignore[attr-defined]
        return self.dict()  # pydantic v1


def build_unified_diff(
    *,
    from_path: str,
    to_path: str,
    old_text: str,
    new_text: str,
    n: int = 3,
) -> str:
    """
    Строит unified diff по двум текстам.
    """
    old_lines = old_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)
    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=str(from_path),
        tofile=str(to_path),
        n=int(n),
    )
    return "".join(diff)
