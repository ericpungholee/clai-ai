"""The immutable image version, not a category prompt, defines mesh inputs."""

VIEW_ORDER = ("front", "front_right", "rear_right", "rear_left", "front_left")
SUPPORTING_VIEWS = VIEW_ORDER[1:]


def view_urls(*, front_url: str | None, metadata: dict | None) -> dict[str, str]:
    if not isinstance(front_url, str) or not front_url.strip():
        raise ValueError("This image is missing its source artifact")
    views = metadata.get("views") if isinstance(metadata, dict) else None
    if views is None or views == {}:
        return {"front": front_url}
    if isinstance(views, dict) and set(views) == {"front"}:
        if views["front"] != front_url:
            raise ValueError("This image has inconsistent source view data")
        return {"front": front_url}
    if not isinstance(views, dict) or any(
        not isinstance(views.get(angle), str) or not views[angle].strip()
        for angle in VIEW_ORDER
    ):
        raise ValueError(
            "This image needs a complete five-view set. Generate a new image."
        )
    if (
        set(views) != set(VIEW_ORDER)
        or views["front"] != front_url
        or len({views[angle] for angle in VIEW_ORDER}) != len(VIEW_ORDER)
    ):
        raise ValueError("This image has inconsistent or duplicate multi-view data")
    return {angle: views[angle] for angle in VIEW_ORDER}


def mesh_view_urls(*, front_url: str | None, metadata: dict | None) -> dict[str, str]:
    views = view_urls(front_url=front_url, metadata=metadata)
    if tuple(views) != VIEW_ORDER:
        raise ValueError("3D requires five coherent views. Generate a new image first.")
    return views
