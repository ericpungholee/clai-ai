from typing import Literal, TypedDict


class TextPart(TypedDict):
    type: Literal["text"]
    text: str


class ConnectPart(TypedDict):
    type: Literal["connect"]
    edge_id: str
    source_node_id: str


type PromptPart = TextPart | ConnectPart


def text_document(text: str) -> list[PromptPart]:
    return [{"type": "text", "text": text}]


def compile_document(document: list[PromptPart], *, has_subject: bool) -> str:
    result: list[str] = []
    image_index = 2 if has_subject else 1
    for part in document:
        if part["type"] == "text":
            result.append(part["text"])
        else:
            result.append(f"image {image_index}")
            image_index += 1
    return "".join(result)


def document_text(document: list[PromptPart]) -> str:
    return "".join(part["text"] if part["type"] == "text" else "@" for part in document)
