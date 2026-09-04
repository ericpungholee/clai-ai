from collections.abc import Mapping

from app.domain.runs import (
    FrozenRunRequest,
    InputSnapshot,
    MaskSnapshot,
    NodeSettings,
    Op,
    VersionSnapshot,
)


def encode_frozen_request(request: FrozenRunRequest) -> dict[str, object]:
    return {
        "node_id": request.node_id,
        "op": request.op.value,
        "prompt_at_runtime": request.prompt_at_runtime,
        "seed": request.seed,
        "settings": {
            "aspect_ratio": request.settings.aspect_ratio,
            "width": request.settings.width,
            "height": request.settings.height,
        },
        "base": _encode_version(request.base) if request.base else None,
        "connects": [_encode_version(version) for version in request.connects],
        "mask": _encode_mask(request.mask) if request.mask else None,
        "input_snapshot": {
            "base_version_id": request.input_snapshot.base_version_id,
            "connect_version_ids": list(request.input_snapshot.connect_version_ids),
            "mask_hash": request.input_snapshot.mask_hash,
        },
        "edit_depth": request.edit_depth,
    }


def decode_frozen_request(payload: Mapping[str, object]) -> FrozenRunRequest:
    settings = _mapping(payload, "settings")
    snapshot = _mapping(payload, "input_snapshot")
    base_value = payload.get("base")
    mask_value = payload.get("mask")
    connect_values = payload.get("connects")
    if not isinstance(connect_values, list):
        raise ValueError("Frozen request connects must be a list")
    connect_ids = snapshot.get("connect_version_ids")
    if not isinstance(connect_ids, list) or not all(
        isinstance(value, str) for value in connect_ids
    ):
        raise ValueError("Frozen request connect IDs must be strings")

    return FrozenRunRequest(
        node_id=_string(payload, "node_id"),
        op=Op(_string(payload, "op")),
        prompt_at_runtime=_string(payload, "prompt_at_runtime"),
        seed=_integer(payload, "seed"),
        settings=NodeSettings(
            aspect_ratio=_string(settings, "aspect_ratio"),
            width=_integer(settings, "width"),
            height=_integer(settings, "height"),
        ),
        base=(
            _decode_version(_as_mapping(base_value, "base"))
            if base_value is not None
            else None
        ),
        connects=tuple(
            _decode_version(_as_mapping(value, "connect")) for value in connect_values
        ),
        mask=(
            _decode_mask(_as_mapping(mask_value, "mask"))
            if mask_value is not None
            else None
        ),
        input_snapshot=InputSnapshot(
            base_version_id=_optional_string(snapshot, "base_version_id"),
            connect_version_ids=tuple(connect_ids),
            mask_hash=_optional_string(snapshot, "mask_hash"),
        ),
        edit_depth=_integer(payload, "edit_depth"),
    )


def _encode_version(version: VersionSnapshot) -> dict[str, object]:
    return {
        "id": version.id,
        "node_id": version.node_id,
        "artifact_url": version.artifact_url,
        "seed": version.seed,
        "edit_depth": version.edit_depth,
    }


def _decode_version(payload: Mapping[str, object]) -> VersionSnapshot:
    return VersionSnapshot(
        id=_string(payload, "id"),
        node_id=_string(payload, "node_id"),
        artifact_url=_string(payload, "artifact_url"),
        seed=_integer(payload, "seed"),
        edit_depth=_integer(payload, "edit_depth"),
    )


def _encode_mask(mask: MaskSnapshot) -> dict[str, object]:
    return {
        "rle": mask.rle,
        "width": mask.width,
        "height": mask.height,
        "base_version_id": mask.base_version_id,
    }


def _decode_mask(payload: Mapping[str, object]) -> MaskSnapshot:
    return MaskSnapshot(
        rle=_string(payload, "rle"),
        width=_integer(payload, "width"),
        height=_integer(payload, "height"),
        base_version_id=_string(payload, "base_version_id"),
    )


def _mapping(payload: Mapping[str, object], key: str) -> Mapping[str, object]:
    return _as_mapping(payload.get(key), key)


def _as_mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"Frozen request {label} must be an object")
    return value


def _string(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise ValueError(f"Frozen request {key} must be a string")
    return value


def _optional_string(payload: Mapping[str, object], key: str) -> str | None:
    value = payload.get(key)
    if value is not None and not isinstance(value, str):
        raise ValueError(f"Frozen request {key} must be a string or null")
    return value


def _integer(payload: Mapping[str, object], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"Frozen request {key} must be an integer")
    return value
