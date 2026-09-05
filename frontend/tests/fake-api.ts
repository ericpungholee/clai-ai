import { createServer } from "node:http";
import type { GraphDocument } from "../lib/graph.ts";
import type { MeshData } from "../lib/meshes.ts";

const project = {
  id: "fixture-project",
  name: "Mask test",
  created_at: "2026-09-04T00:00:00Z",
  updated_at: "2026-09-04T00:00:00Z",
  thumbnail_url: null,
};
function fixture(): GraphDocument {
  const settings = {
    aspect_ratio: "1:1",
    width: 480,
    height: 360,
    whiteBackground: true,
  };
  const subject = {
    id: "subject",
    node_id: "source",
    created_at: project.created_at,
    artifact_url: "http://127.0.0.1:8109/artifacts/subject.svg",
    op: "generate" as const,
    provider: "fake",
    model: "fake",
    endpoint: "fake",
    params: {},
    seed: 1,
    input_snapshot: {
      subject_version_id: null,
      connect_version_ids: [],
      mask_hash: null,
    },
    prompt_at_runtime: "A lamp",
    edit_depth: 0,
    hidden: false,
    branch_node_ids: ["target"],
    masked_outside_change: null,
  };
  return {
    nodes: [
      {
        id: "source",
        document: [{ type: "text", text: "A lamp" }],
        revision: 0,
        deleted: false,
        title: "Desk lamp",
        prompt: "A lamp",
        settings,
        seed: 1,
        active_version_id: "subject",
        position: { x: 0, y: 0 },
        versions: [subject],
        mask: null,
      },
      {
        id: "target",
        document: [{ type: "text", text: "Make the shade orange" }],
        revision: 0,
        deleted: false,
        title: "Change the shade",
        prompt: "Make the shade orange",
        settings,
        seed: null,
        active_version_id: null,
        position: { x: 400, y: 0 },
        versions: [],
        mask: null,
      },
    ],
    edges: [
      {
        id: "wire",
        source_node_id: "source",
        target_node_id: "target",
        role: "subject",
        pin: { mode: "version", version_id: "subject" },
        order: null,
      },
    ],
  };
}
let graph = fixture();
const meshes = new Map<string, MeshData>();

function meshFixture(): Buffer {
  const binary = Buffer.alloc(36);
  [-1, 0, 0, 1, 0, 0, 0, 2, 0].forEach((value, index) =>
    binary.writeFloatLE(value, index * 4),
  );
  const document = {
    asset: { version: "2.0" },
    scene: 0,
    scenes: [{ nodes: [0] }],
    nodes: [{ mesh: 0 }],
    meshes: [{ primitives: [{ attributes: { POSITION: 0 }, material: 0 }] }],
    materials: [{ doubleSided: true }],
    buffers: [{ byteLength: binary.length }],
    bufferViews: [{ buffer: 0, byteOffset: 0, byteLength: binary.length }],
    accessors: [
      {
        bufferView: 0,
        componentType: 5126,
        count: 3,
        type: "VEC3",
        min: [-1, 0, 0],
        max: [1, 2, 0],
      },
    ],
  };
  let json = JSON.stringify(document);
  json += " ".repeat((4 - (json.length % 4)) % 4);
  const encoded = Buffer.from(json);
  const header = Buffer.alloc(20);
  header.write("glTF");
  header.writeUInt32LE(2, 4);
  header.writeUInt32LE(28 + encoded.length + binary.length, 8);
  header.writeUInt32LE(encoded.length, 12);
  header.writeUInt32LE(0x4e4f534a, 16);
  const binHeader = Buffer.alloc(8);
  binHeader.writeUInt32LE(binary.length);
  binHeader.writeUInt32LE(0x004e4942, 4);
  return Buffer.concat([header, encoded, binHeader, binary]);
}

createServer(async (request, response) => {
  response.setHeader("Access-Control-Allow-Origin", "*");
  response.setHeader(
    "Access-Control-Allow-Methods",
    "GET,POST,PATCH,PUT,DELETE,OPTIONS",
  );
  response.setHeader("Access-Control-Allow-Headers", "Content-Type");
  response.setHeader("Content-Type", "application/json");
  const chunks: Buffer[] = [];
  for await (const chunk of request) chunks.push(Buffer.from(chunk));
  const payload = Buffer.concat(chunks).toString();
  const body = payload ? JSON.parse(payload) : null;
  const path = request.url ?? "";
  if (request.method === "OPTIONS") {
    response.writeHead(204).end();
    return;
  }
  if (path === "/reset") {
    graph = fixture();
    meshes.clear();
    response.end("{}");
    return;
  }
  if (path === "/artifacts/mesh.glb") {
    response.setHeader("Content-Type", "model/gltf-binary");
    response.end(meshFixture());
    return;
  }
  if (path.endsWith("/mesh")) {
    const versionId = path.split("/versions/")[1].split("/")[0];
    if (request.method === "POST" && !meshes.has(versionId))
      meshes.set(versionId, {
        version_id: versionId,
        attempt_id: body.attempt_id,
        status: "complete",
        texture: body.texture,
        artifact_url: "http://127.0.0.1:8109/artifacts/mesh.glb",
        preview_url: "http://127.0.0.1:8109/artifacts/subject.svg",
        elapsed_seconds: 42,
        error: null,
      });
    response.end(JSON.stringify(meshes.get(versionId) ?? null));
    return;
  }
  if (path === "/stale") {
    graph.edges[0].pin = { mode: "version", version_id: "new-subject" };
    graph.nodes[0].versions.push({
      ...graph.nodes[0].versions[0],
      id: "new-subject",
    });
    response.end("{}");
    return;
  }
  if (path === "/many-versions") {
    const source = graph.nodes[0];
    const first = source.versions[0];
    source.versions = Array.from({ length: 15 }, (_, index) => ({
      ...first,
      id: index === 0 ? first.id : `version-${index + 1}`,
    }));
    source.active_version_id = "version-15";
    response.end("{}");
    return;
  }
  if (path.endsWith("/visibility")) {
    for (const node of graph.nodes)
      for (const version of node.versions)
        if (path.includes(`/versions/${version.id}/`)) {
          version.hidden = body.hidden;
          if (version.hidden && node.active_version_id === version.id)
            node.active_version_id =
              node.versions.findLast((item) => !item.hidden)?.id ?? null;
        }
    response.writeHead(204).end();
    return;
  }
  if (request.method === "PATCH" && path.includes("/nodes/")) {
    const node = graph.nodes.find((node) =>
      path.endsWith(`/nodes/${node.id}`),
    )!;
    if (body.expected_revision !== node.revision) {
      response
        .writeHead(409)
        .end(JSON.stringify({ detail: "Node changed in another tab" }));
      return;
    }
    Object.assign(node, body, { revision: node.revision + 1 });
    response.end(JSON.stringify(node));
    return;
  }
  if (path === "/artifacts/subject.svg") {
    response.setHeader("Content-Type", "image/svg+xml");
    response.end(
      '<svg xmlns="http://www.w3.org/2000/svg" width="480" height="360"><rect width="480" height="360" fill="#f5f1ea"/><path d="M170 100H310L340 190H140Z" fill="#49505b"/><path d="M240 190V285M200 285H280" stroke="#49505b" stroke-width="12"/></svg>',
    );
    return;
  }
  if (path.endsWith("/selection")) {
    response.end("null");
    return;
  }
  if (path.endsWith("/prompt")) {
    const target = graph.nodes.find((node) =>
      path.includes(`/nodes/${node.id}/`),
    )!;
    if (body.expected_revision !== target.revision) {
      response
        .writeHead(409)
        .end(JSON.stringify({ detail: "Prompt changed in another tab" }));
      return;
    }
    target.document = body.document;
    target.prompt = target.document
      .map((part) => (part.type === "text" ? part.text : "@"))
      .join("");
    target.revision++;
    graph.edges = graph.edges.filter(
      (edge) => edge.target_node_id !== target.id || edge.role !== "connect",
    );
    let order = 0;
    for (const part of target.document)
      if (part.type === "connect")
        graph.edges.push({
          id: part.edge_id,
          source_node_id: part.source_node_id,
          target_node_id: target.id,
          role: "connect",
          pin: { mode: "active" },
          order: order++,
        });
    response.end(JSON.stringify(graph));
    return;
  }
  if (path.endsWith("/mask")) {
    graph.nodes[1].mask = body;
    response.end(JSON.stringify(body));
    return;
  }
  if (path.endsWith("/graph")) {
    response.end(JSON.stringify(graph));
    return;
  }
  if (path === "/api/projects") {
    response.end(JSON.stringify([project]));
    return;
  }
  if (path === "/api/projects/fixture-project") {
    response.end(JSON.stringify(project));
    return;
  }
  response
    .writeHead(404)
    .end(JSON.stringify({ detail: "Unimplemented fake route" }));
}).listen(8109, "127.0.0.1");
