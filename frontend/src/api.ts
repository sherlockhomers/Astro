import axios from "axios";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");
const ACCESS_TOKEN_KEY = "astro_access_token";

const api = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true
});

function getAccessToken() {
  return localStorage.getItem(ACCESS_TOKEN_KEY) || localStorage.getItem("astro_token");
}

function setAccessToken(token: string | null) {
  if (token) {
    localStorage.setItem(ACCESS_TOKEN_KEY, token);
    localStorage.setItem("astro_token", token);
    return;
  }
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem("astro_token");
}

let refreshPromise: Promise<any> | null = null;

api.interceptors.request.use((config) => {
  const token = getAccessToken();
  if (token) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config || {};
    const status = error?.response?.status;
    const url = String(originalRequest.url || "");
    const shouldSkip =
      originalRequest._retry ||
      status !== 401 ||
      url.includes("/api/v1/auth/login") ||
      url.includes("/api/v1/auth/register") ||
      url.includes("/api/v1/auth/refresh") ||
      url.includes("/api/v1/auth/logout");

    if (shouldSkip) {
      throw error;
    }

    originalRequest._retry = true;
    try {
      await ensureSession();
      const token = getAccessToken();
      if (token) {
        originalRequest.headers = originalRequest.headers || {};
        originalRequest.headers.Authorization = `Bearer ${token}`;
      }
      return await api(originalRequest);
    } catch {
      setAccessToken(null);
      throw error;
    }
  }
);

export async function getSystemStatus() {

  const { data } = await api.get("/api/v1/system/status");
  return data;
}

function internalHeaders(internalToken: string) {
  return {
    headers: {
      "X-Internal-Token": internalToken
    }
  };
}

export async function getModelStatus() {
  const { data } = await api.get("/api/v1/model/status");
  return data;
}

export async function loadModel(adapterPath?: string, className?: string) {
  const { data } = await api.post("/api/v1/model/load", {
    adapter_path: adapterPath || null,
    class_name: className || null
  });
  return data;
}

export async function register(username: string, password: string) {
  const { data } = await api.post("/api/v1/auth/register", { username, password });
  return data;
}

export async function login(username: string, password: string) {
  const { data } = await api.post("/api/v1/auth/login", { username, password });
  if (data?.ok && (data?.access_token || data?.token)) {
    setAccessToken(data.access_token || data.token);
  }
  return data;
}

export async function refreshAuth() {
  const { data } = await api.post("/api/v1/auth/refresh");
  if (data?.ok && (data?.access_token || data?.token)) {
    setAccessToken(data.access_token || data.token);
  } else {
    setAccessToken(null);
  }
  return data;
}

export async function ensureSession() {
  const token = getAccessToken();
  if (token) return true;
  if (!refreshPromise) {
    refreshPromise = refreshAuth().finally(() => {
      refreshPromise = null;
    });
  }
  const data = await refreshPromise;
  return Boolean(data?.ok && (data?.access_token || data?.token));
}

export async function me() {
  const { data } = await api.get("/api/v1/auth/me");
  return data;
}

export async function getLandingNews(limit = 6) {
  const { data } = await api.get("/api/v1/landing/news", { params: { limit } });
  return data;
}

export async function getLandingApod() {
  const { data } = await api.get("/api/v1/landing/apod");
  return data;
}

export async function getLandingScienceCards(limit = 8) {
  const { data } = await api.get("/api/v1/landing/science-cards", { params: { limit } });
  return data;
}

export async function getLandingFrontier(perTopic = 15) {
  const { data } = await api.get("/api/v1/landing/frontier", { params: { per_topic: perTopic } });
  return data;
}

export async function updateProfile(username: string) {
  const { data } = await api.patch("/api/v1/auth/profile", { username });
  return data;
}

export async function logout() {
  try {
    await api.post("/api/v1/auth/logout");
  } finally {
    setAccessToken(null);
  }
}

export async function scanCsvRoot(csvRoot: string) {
  const { data } = await api.post("/api/v1/data/scan", { csv_root: csvRoot });
  return data;
}

export async function loadCsvRoot(csvRoot: string) {
  const { data } = await api.post("/api/v1/data/load", {
    csv_root: csvRoot,
    categories: []
  });
  return data;
}

export async function getDataStatus() {
  const { data } = await api.get("/api/v1/data/status");
  return data;
}

export async function askQuestion(question: string, sessionId?: string) {
  const { data } = await api.post("/api/v1/qa/ask", {
    question,
    session_id: sessionId || null
  });
  return data;
}

function parseSseBlock(block: string) {
  const lines = block.split(/\r?\n/);
  let event = "message";
  const dataLines: string[] = [];
  for (const line of lines) {
    if (!line || line.startsWith(":")) continue;
    if (line.startsWith("event:")) {
      event = line.slice("event:".length).trim();
      continue;
    }
    if (line.startsWith("data:")) {
      dataLines.push(line.slice("data:".length).trim());
    }
  }
  if (!dataLines.length) return null;
  const raw = dataLines.join("\n");
  try {
    return { event, payload: JSON.parse(raw) };
  } catch {
    return { event, payload: { raw } };
  }
}

export async function streamQuestion(
  question: string,
  sessionId?: string,
  handlers?: {
    onStatus?: (payload: any) => void;
    onDelta?: (payload: any) => void;
    onDone?: (payload: any) => void;
    onError?: (message: string, payload?: any) => void;
  }
) {
  let token = getAccessToken();
  if (!token) {
    try {
      await ensureSession();
      token = getAccessToken();
    } catch {
      token = null;
    }
  }
  const response = await fetch(`${API_BASE_URL}/api/v1/qa/stream`, {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {})
    },
    body: JSON.stringify({
      question,
      session_id: sessionId || null
    })
  });

  if (!response.ok || !response.body) {
    const fallback = await askQuestion(question, sessionId);
    handlers?.onDone?.(fallback);
    return fallback;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  let donePayload: any = null;
  let streamErrored = false;

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });

    let separatorIndex = buffer.indexOf("\n\n");
    while (separatorIndex >= 0) {
      const block = buffer.slice(0, separatorIndex);
      buffer = buffer.slice(separatorIndex + 2);
      const parsed = parseSseBlock(block);
      if (parsed) {
        const { event, payload } = parsed;
        if (event === "status") {
          handlers?.onStatus?.(payload);
        } else if (event === "delta") {
          handlers?.onDelta?.(payload);
        } else if (event === "done") {
          donePayload = payload;
          handlers?.onDone?.(payload);
        } else if (event === "error") {
          streamErrored = true;
          handlers?.onError?.(payload?.message || "流式问答失败。", payload);
        }
      }
      separatorIndex = buffer.indexOf("\n\n");
    }

    if (done) break;
  }

  if (donePayload) {
    return donePayload;
  }

  if (streamErrored) {
    throw new Error("stream_question_failed");
  }

  const fallback = await askQuestion(question, sessionId);
  handlers?.onDone?.(fallback);
  return fallback;
}

export async function streamQuestionWithImage(
  question: string,
  file: File,
  sessionId?: string,
  handlers?: {
    onStatus?: (payload: any) => void;
    onDelta?: (payload: any) => void;
    onDone?: (payload: any) => void;
    onError?: (message: string, payload?: any) => void;
  }
) {
  let token = getAccessToken();
  if (!token) {
    try {
      await ensureSession();
      token = getAccessToken();
    } catch {
      token = null;
    }
  }

  const form = new FormData();
  form.append("question", question);
  form.append("file", file);
  if (sessionId) {
    form.append("session_id", sessionId);
  }

  const response = await fetch(`${API_BASE_URL}/api/v1/qa/stream-with-image`, {
    method: "POST",
    credentials: "include",
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {})
    },
    body: form
  });

  if (!response.ok || !response.body) {
    const fallback = await askWithImage(question, file, sessionId);
    handlers?.onDone?.(fallback);
    return fallback;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  let donePayload: any = null;
  let streamErrored = false;

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });

    let separatorIndex = buffer.indexOf("\n\n");
    while (separatorIndex >= 0) {
      const block = buffer.slice(0, separatorIndex);
      buffer = buffer.slice(separatorIndex + 2);
      const parsed = parseSseBlock(block);
      if (parsed) {
        const { event, payload } = parsed;
        if (event === "status") {
          handlers?.onStatus?.(payload);
        } else if (event === "delta") {
          handlers?.onDelta?.(payload);
        } else if (event === "done") {
          donePayload = payload;
          handlers?.onDone?.(payload);
        } else if (event === "error") {
          streamErrored = true;
          handlers?.onError?.(payload?.message || "图片问答失败。", payload);
        }
      }
      separatorIndex = buffer.indexOf("\n\n");
    }

    if (done) break;
  }

  if (donePayload) {
    return donePayload;
  }

  if (streamErrored) {
    throw new Error("stream_question_with_image_failed");
  }

  const fallback = await askWithImage(question, file, sessionId);
  handlers?.onDone?.(fallback);
  return fallback;
}

export async function askWithImage(question: string, file: File, sessionId?: string) {
  const form = new FormData();
  form.append("question", question);
  form.append("file", file);
  if (sessionId) {
    form.append("session_id", sessionId);
  }
  const { data } = await api.post("/api/v1/qa/ask-with-image", form, {
    headers: { "Content-Type": "multipart/form-data" }
  });
  return data;
}

export async function searchKnowledge(query: string, topK = 5) {
  const { data } = await api.post("/api/v1/retrieval/search", {
    query,
    top_k: topK,
    image_hint: null
  });
  return data;
}

export async function searchHybrid(query: string, imageHint: string, topK = 5) {
  const { data } = await api.post("/api/v1/retrieval/search", {
    query,
    top_k: topK,
    image_hint: imageHint
  });
  return data;
}

export async function getExploreBundle(query: string, imageHint?: string | null) {
  const { data } = await api.post("/api/v1/explore/query", {
    query,
    image_hint: imageHint || null
  });
  return data;
}

export async function getRetrievalVectorSchema() {
  const { data } = await api.get("/api/v1/retrieval/vector-schema");
  return data;
}

export async function triggerBuildGraph(csvRoot: string) {
  const { data } = await api.post("/api/v1/graph/build", {
    csv_root: csvRoot,
    categories: [],
    write_neo4j: false
  });
  return data;
}

export async function getGraphStatus() {
  const { data } = await api.get("/api/v1/graph/status");
  return data;
}

export async function exportGraphCypher(outputPath: string) {
  const { data } = await api.post("/api/v1/graph/export-cypher", { output_path: outputPath });
  return data;
}

export async function getGraphSchemaSummary() {
  const { data } = await api.get("/api/v1/graph/schema-summary");
  return data;
}

export async function getGraphPaths(topK = 20) {
  const { data } = await api.get("/api/v1/graph/paths", {
    params: { top_k: topK }
  });
  return data;
}

export async function findGraphPath(source: string, target: string, maxHops = 4) {
  const { data } = await api.get("/api/v1/graph/path", {
    params: { source, target, max_hops: maxHops }
  });
  return data;
}

export async function findGraphMultiPath(source: string, target: string, maxHops = 4, maxPaths = 6) {
  const { data } = await api.get("/api/v1/graph/multi-path", {
    params: { source, target, max_hops: maxHops, max_paths: maxPaths }
  });
  return data;
}

export async function getVisualizationGraph(maxNodes = 220, maxLinks = 900, signal?: AbortSignal) {
  const { data } = await api.get("/api/v1/visualization/graph", {
    params: { max_nodes: maxNodes, max_links: maxLinks },
    timeout: 20000,
    signal
  });
  return data;
}

export async function getVisualizationSubgraph(
  query: string,
  maxNodes = 600,
  maxLinks = 4000,
  maxHops = 2,
  includeRelated = false,
  signal?: AbortSignal
) {
  const { data } = await api.get("/api/v1/visualization/subgraph", {
    params: {
      query,
      max_nodes: maxNodes,
      max_links: maxLinks,
      max_hops: maxHops,
      include_related: includeRelated
    },
    timeout: 20000,
    signal
  });
  return data;
}

export async function compareEntities(nameA: string, nameB: string) {
  const { data } = await api.get("/api/v1/visualization/compare", {
    params: { name_a: nameA, name_b: nameB }
  });
  return data;
}

export async function getTimeline(limit = 200) {
  const { data } = await api.get("/api/v1/visualization/timeline", {
    params: { limit }
  });
  return data;
}

export async function getStarfield(limit = 800) {
  const { data } = await api.get("/api/v1/visualization/starfield", {
    params: { limit }
  });
  return data;
}

export async function getUserHistory(limit = 50, offset = 0) {
  const { data } = await api.get("/api/v1/user/history", { params: { limit, offset } });
  return data;
}

export async function getUserOverview() {
  const { data } = await api.get("/api/v1/user/overview");
  return data;
}

export async function saveFavorite(payload: {
  title: string;
  category?: string | null;
  image_url?: string | null;
  source_query?: string | null;
}) {
  const { data } = await api.post("/api/v1/user/favorites", payload);
  return data;
}

export async function deleteFavorite(favoriteId: number) {
  const { data } = await api.delete(`/api/v1/user/favorites/${favoriteId}`);
  return data;
}

export async function deleteHistoryItem(historyId: number) {
  const { data } = await api.delete(`/api/v1/user/history/${historyId}`);
  return data;
}

export async function imageSearchByText(query: string, page = 1, pageSize = 12) {
  const { data } = await api.get("/api/v1/image/search-by-text", {
    params: { query, page, page_size: pageSize }
  });
  return data;
}

export async function imageSearchByImage(file: File, page = 1, pageSize = 12) {
  const form = new FormData();
  form.append("file", file);
  const { data } = await api.post(
    `/api/v1/image/search-by-image?page=${page}&page_size=${pageSize}`,
    form,
    {
      headers: { "Content-Type": "multipart/form-data" }
    }
  );
  return data;
}

export async function getImageVectorStatus() {
  const { data } = await api.get("/api/v1/image/vector-status");
  return data;
}

export async function getImageIndexStatus() {
  const { data } = await api.get("/api/v1/image/index-status");
  return data;
}

export async function triggerImageIndex(force = false) {
  const { data } = await api.post(`/api/v1/image/index-trigger?force=${force ? "true" : "false"}`);
  return data;
}

export async function getModel3D(query: string) {
  const { data } = await api.get("/api/v1/visualization/model3d", {
    params: { query }
  });
  return data;
}

export async function getInternalCapabilityReport(internalToken: string) {
  const { data } = await api.get("/api/v1/system/capability-report", internalHeaders(internalToken));
  return data;
}

export async function getEvaluationReport(internalToken: string) {
  const { data } = await api.get("/api/v1/eval/report", internalHeaders(internalToken));
  return data;
}

export async function runEvaluation(internalToken: string, sampleSize = 12, useCache = true) {
  const { data } = await api.post(
    "/api/v1/eval/run",
    {
      sample_size: sampleSize,
      use_cache: useCache
    },
    internalHeaders(internalToken)
  );
  return data;
}

