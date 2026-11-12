async function request(path, options = {}) {
  const res = await fetch(path, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });
  let data = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  if (!res.ok) {
    const err = new Error((data && data.error) || `Request failed (${res.status})`);
    err.status = res.status;
    err.data = data;
    throw err;
  }
  return data;
}

export const api = {
  overview: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/api/overview${qs ? `?${qs}` : ""}`);
  },
  startQuiz: (body) =>
    request("/api/quiz", { method: "POST", body: JSON.stringify(body) }),
  answerQuiz: (body) =>
    request("/api/quiz?action=answer", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  startDrill: (body) =>
    request("/api/drill", { method: "POST", body: JSON.stringify(body) }),
  answerDrill: (body) =>
    request("/api/drill?action=answer", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  undoDrill: (body) =>
    request("/api/drill?action=undo", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  drillStats: () => request("/api/drill?action=stats"),
  getDrill: (sessionId) =>
    request(`/api/drill?session_id=${encodeURIComponent(sessionId)}`),
  levels: () => request("/api/course?action=levels"),
  courseLevel: (level) => request(`/api/course?level=${encodeURIComponent(level)}`),
  startCourse: (level) =>
    request("/api/course?action=start", { method: "POST", body: JSON.stringify({ level }) }),
  courseQueue: (level, mode) =>
    request(`/api/course?action=queue&level=${encodeURIComponent(level)}&mode=${encodeURIComponent(mode)}`),
  sky: () => request("/api/course?action=sky"),
  gateStatus: () => request("/api/gate"),
  gateStart: () => request("/api/gate?action=start", { method: "POST", body: "{}" }),
  gateSeen: (gateId, questionId) =>
    request("/api/gate?action=seen", { method: "POST", body: JSON.stringify({ gate_id: gateId, question_id: questionId }) }),
  gateFinish: (gateId) =>
    request("/api/gate?action=finish", { method: "POST", body: JSON.stringify({ gate_id: gateId }) }),
  daily: (summary = false) => request(`/api/course?action=daily${summary ? "&summary=1" : ""}`),
  setDailySize: (size) =>
    request("/api/course?action=daily-size", { method: "POST", body: JSON.stringify({ size }) }),
  courseAnswer: (body) =>
    request("/api/course?action=answer", { method: "POST", body: JSON.stringify(body) }),
  inspect: (subjectId) =>
    request(`/api/inspect?subject_id=${encodeURIComponent(subjectId)}`),
  readIndex: () => request("/api/read"),
  readLevel: (level) => request(`/api/read?action=level&level=${encodeURIComponent(level)}`),
  readPassage: (id) => request(`/api/read?action=passage&id=${encodeURIComponent(id)}`),
  readDaily: () => request("/api/read?action=daily"),
  kanjiWeb: (level) => request(`/api/read?action=web&level=${encodeURIComponent(level)}`),
  readLookup: (body) =>
    request("/api/read?action=lookup", { method: "POST", body: JSON.stringify(body) }),
  readDictation: (body) =>
    request("/api/read?action=dictation", { method: "POST", body: JSON.stringify(body) }),
  readFinish: (body) =>
    request("/api/read?action=finish", { method: "POST", body: JSON.stringify(body) }),
  readCustom: (body) =>
    request("/api/read?action=custom", { method: "POST", body: JSON.stringify(body) }),
  readSearch: (q) => request(`/api/read?action=search&q=${encodeURIComponent(q)}`),
  readFeed: (offset = 0) => request(`/api/read?action=feed&offset=${encodeURIComponent(offset)}`),
  readStory: (band) => request(`/api/read?action=story&band=${encodeURIComponent(band)}`),
  readFeedAgain: (subjectId) =>
    request("/api/read?action=feed", { method: "POST", body: JSON.stringify({ subject_id: subjectId }) }),
};
