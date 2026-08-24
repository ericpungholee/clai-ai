import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def validate_name(cls, name: str) -> str:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("Project name cannot be empty")
        return normalized_name


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    created_at: datetime
    updated_at: datetime
    thumbnail_url: HttpUrl | None
