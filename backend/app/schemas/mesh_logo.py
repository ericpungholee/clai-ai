from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

Finite = Annotated[float, Field(allow_inf_nan=False)]
Unit = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class LogoBounds(BaseModel):
    x: Unit
    y: Unit
    width: Annotated[float, Field(gt=0, le=1, allow_inf_nan=False)]
    height: Annotated[float, Field(gt=0, le=1, allow_inf_nan=False)]

    @model_validator(mode="after")
    def contained(self) -> Self:
        if self.x + self.width > 1.000001 or self.y + self.height > 1.000001:
            raise ValueError("Crop bounds must be inside the source image")
        return self


class LogoSource(BaseModel):
    url: str = Field(max_length=2048)
    bounds: LogoBounds
    subjectBounds: LogoBounds | None = None
    mode: Literal["auto", "manual"]


class LogoCrop(BaseModel):
    # Incoming manual crops may be inline PNGs; persisted crops are stored URLs.
    dataUrl: str = Field(max_length=8 * 1024 * 1024)
    width: int = Field(ge=1, le=4096)
    height: int = Field(ge=1, le=4096)


class LogoPlacement(BaseModel):
    meshIndex: int = Field(ge=0)
    position: tuple[Finite, Finite, Finite]
    orientation: tuple[Finite, Finite, Finite, Finite]

    @model_validator(mode="after")
    def normalized(self) -> Self:
        if abs(sum(v * v for v in self.orientation) - 1) > 0.01:
            raise ValueError("Placement orientation must be a unit quaternion")
        if any(abs(v) > 2 for v in self.position):
            raise ValueError("Placement is outside the normalized model")
        return self


class MeshDecal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: LogoSource
    crop: LogoCrop
    placement: LogoPlacement | None = None
    size: Annotated[float, Field(gt=0, le=1, allow_inf_nan=False)] = 0.25
    rotation: Annotated[float, Field(ge=-180, le=180, allow_inf_nan=False)] = 0


class LogoPreservation(BaseModel):
    status: Literal["ready", "not_found", "failed", "removed"]
    decal: MeshDecal | None = None
