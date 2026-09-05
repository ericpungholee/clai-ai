import { randomInt } from "node:crypto";
import { createServer } from "node:http";
import type { GraphDocument, RunJob } from "../lib/graph.ts";
import type { MeshData } from "../lib/meshes.ts";

const project = {
  id: "fixture-project",
  name: "Mask test",
  created_at: "2026-09-04T00:00:00Z",
  updated_at: "2026-09-04T00:00:00Z",
  thumbnail_url: null,
};
function previewForGraph(graph: GraphDocument, nodeId: string) {
  const node = graph.nodes.find((node) => node.id === nodeId)!;
  const subject = graph.edges.find(
    (edge) => edge.target_node_id === nodeId && edge.role === "subject",
  );
  const refs = node.document.flatMap((part) =>
    part.type === "connect"
      ? [
          graph.nodes.find((source) => source.id === part.source_node_id)
            ?.active_version_id ?? null,
        ]
      : [],
  );
  const mask =
    node.mask && node.mask.rle === `1 ${node.mask.width * node.mask.height}`
      ? null
      : node.mask;
  const op = subject
    ? mask
      ? "edit_inpaint"
      : refs.length
        ? "edit_ref_guided"
        : "edit_instruct"
    : refs.length
      ? "generate_ref"
      : "generate";
  return { op };
}

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
    branch_node_ids: ["target"],
    masked_outside_change: null,
  };
  const result: GraphDocument = {
    nodes: [
      {
        id: "source",
        document: [{ type: "text", text: "A lamp" }],
        revision: 0,
        deleted: false,
        run: null,
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
        run: null,
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
  return result;
}

let graph = fixture();
const meshes = new Map<string, MeshData>();
const runs = new Map<string, { job: RunJob; prompt: string; seed: number }>();
let projectDeleted = false;

function meshFixture(textured: boolean): Buffer {
  const binary = Buffer.alloc(60);
  [-1, 0, 0, 1, 0, 0, 0, 2, 0].forEach((value, index) =>
    binary.writeFloatLE(value, index * 4),
  );
  [0, 0, 1, 0, 0.5, 1].forEach((value, index) =>
    binary.writeFloatLE(value, 36 + index * 4),
  );
  const document = {
    asset: { version: "2.0" },
    scene: 0,
    scenes: [{ nodes: [0] }],
    nodes: [{ mesh: 0 }],
    meshes: [
      {
        primitives: [
          { attributes: { POSITION: 0, TEXCOORD_0: 1 }, material: 0 },
        ],
      },
    ],
    materials: [
      {
        doubleSided: true,
        pbrMetallicRoughness: {
          metallicFactor: 0,
          roughnessFactor: 1,
          ...(textured ? { baseColorTexture: { index: 0 } } : {}),
        },
      },
    ],
    textures: textured ? [{ source: 0 }] : [],
    images: textured
      ? [
          {
            uri: "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAFklEQVR4nGP8n8fA+Og/E+Oj///lGAEt3wZT5z8djgAAAABJRU5ErkJggg==",
          },
        ]
      : [],
    buffers: [{ byteLength: binary.length }],
    bufferViews: [
      { buffer: 0, byteOffset: 0, byteLength: 36 },
      { buffer: 0, byteOffset: 36, byteLength: 24 },
    ],
    accessors: [
      {
        bufferView: 0,
        componentType: 5126,
        count: 3,
        type: "VEC3",
        min: [-1, 0, 0],
        max: [1, 2, 0],
      },
      { bufferView: 1, componentType: 5126, count: 3, type: "VEC2" },
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
    runs.clear();
    projectDeleted = false;
    project.name = "Mask test";
    response.end("{}");
    return;
  }
  if (path === "/empty-projects") {
    projectDeleted = true;
    response.end("{}");
    return;
  }
  if (path === "/finish-run" || path === "/fail-run") {
    const entry = [...runs.values()].at(-1)!;
    const node = graph.nodes.find((node) => node.id === entry.job.node_id)!;
    if (path === "/fail-run") {
      entry.job.status = "failed";
      entry.job.error = "Fixture provider could not finish";
    } else {
      const version = {
        ...fixture().nodes[0].versions[0],
        id: `result-${entry.job.id}`,
        artifact_url: `http://127.0.0.1:8109/artifacts/result-${entry.job.id}.svg`,
        node_id: node.id,
        prompt_at_runtime: entry.prompt,
        seed: entry.seed,
        created_at: new Date().toISOString(),
        branch_node_ids: [],
        masked_outside_change: node.mask ? 0 : null,
      };
      if (node.title === "Untitled node")
        node.title = node.prompt
          .trim()
          .split(/\s+/)
          .slice(0, 5)
          .join(" ")
          .slice(0, 60);
      node.versions.push(version);
      node.active_version_id = version.id;
      entry.job.status = "complete";
      entry.job.version_id = version.id;
    }
    entry.job.completed_at = new Date().toISOString();
    node.run = entry.job;
    response.end("{}");
    return;
  }
  const targetId = path.match(/\/nodes\/([^/]+)/)?.[1];
  const targetNode = graph.nodes.find((node) => node.id === targetId);
  const edit =
    ["PATCH", "PUT", "DELETE"].includes(request.method ?? "") &&
    (path.endsWith("/prompt") ||
      path.endsWith("/mask") ||
      path.endsWith("/subject") ||
      (request.method === "PATCH" &&
        ["prompt", "settings", "seed", "subject", "mask"].some(
          (field) => field in body,
        )));
  if (
    edit &&
    targetNode &&
    (targetNode.versions.length ||
      (targetNode.run &&
        !["complete", "failed"].includes(targetNode.run.status)))
  ) {
    response.writeHead(409).end(
      JSON.stringify({
        detail:
          "This node is frozen. Continue editing or Revise prompt to make a new node.",
      }),
    );
    return;
  }
  if (
    edit &&
    targetNode &&
    ((path.endsWith("/mask") &&
      body &&
      targetNode.document.some((part) => part.type === "connect")) ||
      (path.endsWith("/prompt") &&
        targetNode.mask &&
        body.document.some(
          (part: { type: string }) => part.type === "connect",
        )))
  ) {
    response.writeHead(409).end(
      JSON.stringify({
        detail:
          "Area selections can't be combined with references. Remove the selection first.",
      }),
    );
    return;
  }
  if (path.endsWith("/run-preview")) {
    const id = path.split("/nodes/")[1].split("/")[0];
    response.end(JSON.stringify(previewForGraph(graph, id)));
    return;
  }
  if (path.endsWith("/runs") && request.method === "POST") {
    const node = graph.nodes.find((node) =>
      path.includes(`/nodes/${node.id}/`),
    )!;
    if (node.versions.length) {
      response.writeHead(409).end(
        JSON.stringify({
          detail:
            "This node already has an image. Continue editing to make a new node.",
        }),
      );
      return;
    }
    const job: RunJob = {
      id: crypto.randomUUID(),
      node_id: node.id,
      status: "queued",
      op: "edit_instruct",
      attempts: 0,
      error: null,
      version_id: null,
      created_at: new Date().toISOString(),
      completed_at: null,
    };
    node.run = job;
    runs.set(job.id, {
      job,
      prompt: node.prompt,
      seed: node.seed ?? 1,
    });
    response.writeHead(202).end(JSON.stringify(job));
    return;
  }
  if (path.includes("/runs/")) {
    const entry = runs.get(path.split("/runs/")[1])!;
    response.end(JSON.stringify(entry.job));
    return;
  }
  if (path.endsWith("/nodes") && request.method === "POST") {
    const node = {
      ...fixture().nodes[1],
      id: body.id,
      title: "Untitled node",
      prompt: "",
      document: [],
      position: body.position,
    };
    graph.nodes.push(node);
    response.writeHead(201).end(JSON.stringify(node));
    return;
  }
  if (path.endsWith("/branches")) {
    const imageId = path.split("/versions/")[1].split("/")[0];
    const source = graph.nodes.find((node) =>
      node.versions.some((image) => image.id === imageId),
    )!;
    const node = {
      ...structuredClone(fixture().nodes[1]),
      id: body.id,
      title: "Untitled node",
      document: [],
      prompt: "",
      position: body.position,
    };
    const edge = {
      id: crypto.randomUUID(),
      source_node_id: source.id,
      target_node_id: node.id,
      role: "subject" as const,
      pin: { mode: "version" as const, version_id: imageId },
      order: null,
    };
    graph.nodes.push(node);
    graph.edges.push(edge);
    response.writeHead(201).end(JSON.stringify({ node, edge }));
    return;
  }
  if (path.endsWith("/duplicate")) {
    const source = graph.nodes.find((node) =>
      path.includes(`/nodes/${node.id}/`),
    )!;
    const node = {
      ...structuredClone(source),
      id: body.id,
      title: `${source.title} · copy`,
      seed: body.fresh_seed ? randomInt(2 ** 32) : source.seed,
      position: body.position,
      versions: [],
      active_version_id: null,
      revision: 0,
      run: null,
    };
    node.document = node.document.map((part) =>
      part.type === "connect"
        ? { ...part, edge_id: crypto.randomUUID() }
        : part,
    );
    for (const edge of graph.edges.filter(
      (edge) => edge.target_node_id === source.id,
    )) {
      graph.edges.push({
        ...structuredClone(edge),
        id:
          edge.role === "connect"
            ? node.document.flatMap((part) =>
                part.type === "connect" &&
                part.source_node_id === edge.source_node_id
                  ? [part.edge_id]
                  : [],
              )[0]
            : crypto.randomUUID(),
        target_node_id: node.id,
      });
    }
    graph.nodes.push(node);
    response.writeHead(201).end(JSON.stringify(node));
    return;
  }
  if (request.method === "DELETE" && /\/nodes\/[^/]+$/.test(path)) {
    const node = graph.nodes.find((node) =>
      path.endsWith(`/nodes/${node.id}`),
    )!;
    node.deleted = true;
    response.writeHead(204).end();
    return;
  }
  if (request.method === "PUT" && path.endsWith("/subject")) {
    const id = path.split("/nodes/")[1].split("/")[0];
    graph.edges = graph.edges.filter(
      (edge) => edge.target_node_id !== id || edge.role !== "subject",
    );
    const edge = {
      id: `subject-${id}`,
      source_node_id: body.source_node_id,
      target_node_id: id,
      role: "subject" as const,
      pin: { mode: "version" as const, version_id: body.version_id },
      order: null,
    };
    graph.edges.push(edge);
    response.end(JSON.stringify(edge));
    return;
  }
  if (request.method === "DELETE" && path.endsWith("/subject")) {
    const id = path.split("/nodes/")[1].split("/")[0];
    graph.edges = graph.edges.filter(
      (edge) => edge.target_node_id !== id || edge.role !== "subject",
    );
    response.writeHead(204).end();
    return;
  }
  if (path === "/artifacts/mesh.glb" || path === "/artifacts/grey-mesh.glb") {
    response.setHeader("Content-Type", "model/gltf-binary");
    response.end(meshFixture(path === "/artifacts/mesh.glb"));
    return;
  }
  if (path.endsWith("/mesh")) {
    const versionId = path.split("/versions/")[1].split("/")[0];
    const cached = meshes.get(versionId);
    const texture = body?.texture ?? "standard";
    if (
      request.method === "POST" &&
      (!cached ||
        (cached.status === "complete" &&
          cached.texture === "no" &&
          texture === "standard" &&
          cached.attempt_id !== body.attempt_id))
    )
      meshes.set(versionId, {
        version_id: versionId,
        attempt_id: body.attempt_id,
        status: "complete",
        texture,
        artifact_url: `http://127.0.0.1:8109/artifacts/${texture === "no" ? "grey-mesh" : "mesh"}.glb`,
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
  if (path === "/large-canvas") {
    const source = fixture().nodes[0];
    graph.nodes = Array.from({ length: 50 }, (_, index) => ({
      ...structuredClone(source),
      id: `concept-${index}`,
      title: `Concept ${index + 1}`,
      active_version_id: `version-${index}`,
      position: { x: (index % 10) * 380, y: Math.floor(index / 10) * 850 },
      versions: [
        {
          ...source.versions[0],
          id: `version-${index}`,
          node_id: `concept-${index}`,
          branch_node_ids: [],
        },
      ],
    }));
    graph.edges = [];
    response.end("{}");
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
  if (path.startsWith("/artifacts/result-")) {
    const id = path.slice("/artifacts/result-".length).replace(/\.svg$/, "");
    const shade = runs.get(id)?.prompt.toLowerCase().includes("orange")
      ? "#f97316"
      : "#49505b";
    response.setHeader("Content-Type", "image/svg+xml");
    response.end(
      `<svg xmlns="http://www.w3.org/2000/svg" width="480" height="360"><rect width="480" height="360" fill="#f5f1ea"/><path d="M170 100H310L340 190H140Z" fill="${shade}"/><path d="M240 190V285M200 285H280" stroke="#49505b" stroke-width="12"/></svg>`,
    );
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
    targetNode!.mask = body;
    response.end(JSON.stringify(body));
    return;
  }
  if (path.endsWith("/graph")) {
    response.end(JSON.stringify(graph));
    return;
  }
  if (path === "/api/projects") {
    if (request.method === "POST") {
      projectDeleted = false;
      project.name = body.name;
      graph = { nodes: [], edges: [] };
      response.writeHead(201).end(JSON.stringify(project));
      return;
    }
    response.end(JSON.stringify(projectDeleted ? [] : [project]));
    return;
  }
  if (path === "/api/projects/fixture-project") {
    if (request.method === "DELETE") {
      projectDeleted = true;
      response.writeHead(204).end();
      return;
    }
    if (request.method === "PATCH") project.name = body.name;
    response.end(JSON.stringify(project));
    return;
  }
  response
    .writeHead(404)
    .end(JSON.stringify({ detail: "Unimplemented fake route" }));
}).listen(8109, "127.0.0.1");
