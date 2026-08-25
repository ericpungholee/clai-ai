import uuid

from fastapi.testclient import TestClient


def create_project(client: TestClient, name: str = "Lamp") -> str:
    response = client.post("/api/projects", json={"name": name})
    assert response.status_code == 201
    return response.json()["id"]


def prompt_node(
    node_id: str,
    text: str = "Minimal aluminum desk lamp",
    x: float = 120,
    y: float = 200,
) -> dict[str, object]:
    return {
        "id": node_id,
        "type": "prompt",
        "position": {"x": x, "y": y},
        "data": {"text": text},
    }


def image_node(node_id: str, x: float = 420, y: float = 200) -> dict[str, object]:
    return {
        "id": node_id,
        "type": "image",
        "position": {"x": x, "y": y},
        "data": {},
    }


def model_node(node_id: str, x: float = 720, y: float = 200) -> dict[str, object]:
    return {
        "id": node_id,
        "type": "model3d",
        "position": {"x": x, "y": y},
        "data": {},
    }


def graph_edge(edge_id: str, source: str, target: str) -> dict[str, object]:
    return {
        "id": edge_id,
        "source": source,
        "target": target,
        "source_handle": "source",
        "target_handle": "target",
    }


def test_empty_project_returns_empty_graph(client: TestClient) -> None:
    project_id = create_project(client)

    response = client.get(f"/api/projects/{project_id}/graph")

    assert response.status_code == 200
    assert response.json() == {"nodes": [], "edges": []}


def test_saved_nodes_and_edges_survive_retrieval(client: TestClient) -> None:
    project_id = create_project(client)
    source_id = str(uuid.uuid4())
    target_id = str(uuid.uuid4())
    model_id = str(uuid.uuid4())
    edge_id = str(uuid.uuid4())
    graph = {
        "nodes": [
            prompt_node(source_id),
            image_node(target_id),
            model_node(model_id),
        ],
        "edges": [graph_edge(edge_id, source_id, target_id)],
    }

    save_response = client.put(f"/api/projects/{project_id}/graph", json=graph)
    load_response = client.get(f"/api/projects/{project_id}/graph")

    assert save_response.status_code == 200
    assert load_response.status_code == 200
    assert load_response.json() == save_response.json()
    assert {node["id"]: node for node in load_response.json()["nodes"]} == {
        node["id"]: node for node in graph["nodes"]
    }
    assert load_response.json()["edges"] == graph["edges"]


def test_graph_save_updates_prompt_and_position_without_duplicates(
    client: TestClient,
) -> None:
    project_id = create_project(client)
    node_id = str(uuid.uuid4())
    initial_graph = {"nodes": [prompt_node(node_id)], "edges": []}
    latest_graph = {
        "nodes": [prompt_node(node_id, text="Portable task light", x=-40, y=315.5)],
        "edges": [],
    }

    first_response = client.put(
        f"/api/projects/{project_id}/graph",
        json=initial_graph,
    )
    repeat_response = client.put(
        f"/api/projects/{project_id}/graph",
        json=initial_graph,
    )
    latest_response = client.put(
        f"/api/projects/{project_id}/graph",
        json=latest_graph,
    )

    assert first_response.status_code == 200
    assert repeat_response.json() == first_response.json()
    assert latest_response.status_code == 200
    assert latest_response.json() == latest_graph
    assert client.get(f"/api/projects/{project_id}/graph").json() == latest_graph


def test_repeated_save_does_not_duplicate_edges(client: TestClient) -> None:
    project_id = create_project(client)
    source_id = str(uuid.uuid4())
    target_id = str(uuid.uuid4())
    edge_id = str(uuid.uuid4())
    graph = {
        "nodes": [prompt_node(source_id), image_node(target_id)],
        "edges": [graph_edge(edge_id, source_id, target_id)],
    }

    first_response = client.put(f"/api/projects/{project_id}/graph", json=graph)
    second_response = client.put(f"/api/projects/{project_id}/graph", json=graph)

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert {node["id"]: node for node in second_response.json()["nodes"]} == {
        node["id"]: node for node in graph["nodes"]
    }
    assert second_response.json()["edges"] == graph["edges"]
    assert len(second_response.json()["edges"]) == 1


def test_edge_removal_is_persistent(client: TestClient) -> None:
    project_id = create_project(client)
    source_id = str(uuid.uuid4())
    target_id = str(uuid.uuid4())
    graph = {
        "nodes": [prompt_node(source_id), image_node(target_id)],
        "edges": [graph_edge(str(uuid.uuid4()), source_id, target_id)],
    }

    client.put(f"/api/projects/{project_id}/graph", json=graph)
    response = client.put(
        f"/api/projects/{project_id}/graph",
        json={"nodes": graph["nodes"], "edges": []},
    )

    assert response.status_code == 200
    assert response.json()["edges"] == []
    assert client.get(f"/api/projects/{project_id}/graph").json()["edges"] == []


def test_removing_node_removes_connected_edge(client: TestClient) -> None:
    project_id = create_project(client)
    source_id = str(uuid.uuid4())
    target_id = str(uuid.uuid4())
    graph = {
        "nodes": [prompt_node(source_id), image_node(target_id)],
        "edges": [graph_edge(str(uuid.uuid4()), source_id, target_id)],
    }

    client.put(f"/api/projects/{project_id}/graph", json=graph)
    response = client.put(
        f"/api/projects/{project_id}/graph",
        json={"nodes": [graph["nodes"][0]], "edges": []},
    )

    assert response.status_code == 200
    assert response.json() == {"nodes": [graph["nodes"][0]], "edges": []}
    assert client.get(f"/api/projects/{project_id}/graph").json() == response.json()


def test_graph_routes_return_not_found_for_missing_project(
    client: TestClient,
) -> None:
    project_id = uuid.uuid4()

    get_response = client.get(f"/api/projects/{project_id}/graph")
    put_response = client.put(
        f"/api/projects/{project_id}/graph",
        json={"nodes": [], "edges": []},
    )

    assert get_response.status_code == 404
    assert put_response.status_code == 404
    assert get_response.json() == {"detail": "Project not found"}
    assert put_response.json() == {"detail": "Project not found"}


def test_graph_rejects_invalid_node_type(client: TestClient) -> None:
    project_id = create_project(client)
    node = prompt_node(str(uuid.uuid4()))
    node["type"] = "generic"

    response = client.put(
        f"/api/projects/{project_id}/graph",
        json={"nodes": [node], "edges": []},
    )

    assert response.status_code == 422
    assert client.get(f"/api/projects/{project_id}/graph").json() == {
        "nodes": [],
        "edges": [],
    }


def test_graph_rejects_edge_with_missing_endpoint(client: TestClient) -> None:
    project_id = create_project(client)
    source_id = str(uuid.uuid4())

    response = client.put(
        f"/api/projects/{project_id}/graph",
        json={
            "nodes": [prompt_node(source_id)],
            "edges": [graph_edge(str(uuid.uuid4()), source_id, str(uuid.uuid4()))],
        },
    )

    assert response.status_code == 422
    assert "Edge endpoints" in response.text


def test_graph_rejects_non_finite_position(client: TestClient) -> None:
    project_id = create_project(client)
    node_id = uuid.uuid4()
    payload = (
        '{"nodes":[{"id":"'
        f"{node_id}"
        '","type":"prompt","position":{"x":1e309,"y":0},'
        '"data":{"text":"Lamp"}}],"edges":[]}'
    )

    response = client.put(
        f"/api/projects/{project_id}/graph",
        content=payload,
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422
    assert client.get(f"/api/projects/{project_id}/graph").json() == {
        "nodes": [],
        "edges": [],
    }


def test_graph_rejects_ids_owned_by_another_project(client: TestClient) -> None:
    first_project_id = create_project(client, "First")
    second_project_id = create_project(client, "Second")
    node_id = str(uuid.uuid4())
    first_graph = {"nodes": [prompt_node(node_id)], "edges": []}
    client.put(f"/api/projects/{first_project_id}/graph", json=first_graph)

    response = client.put(
        f"/api/projects/{second_project_id}/graph",
        json=first_graph,
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Graph contains resources owned by another project"
    }
    assert client.get(f"/api/projects/{second_project_id}/graph").json() == {
        "nodes": [],
        "edges": [],
    }


def test_invalid_graph_does_not_replace_persisted_graph(client: TestClient) -> None:
    project_id = create_project(client)
    node_id = str(uuid.uuid4())
    graph = {"nodes": [prompt_node(node_id)], "edges": []}
    client.put(f"/api/projects/{project_id}/graph", json=graph)

    invalid_response = client.put(
        f"/api/projects/{project_id}/graph",
        json={
            "nodes": [],
            "edges": [graph_edge(str(uuid.uuid4()), node_id, str(uuid.uuid4()))],
        },
    )

    assert invalid_response.status_code == 422
    assert client.get(f"/api/projects/{project_id}/graph").json() == graph
