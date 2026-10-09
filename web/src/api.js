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
  getDrill: (sessionId) =>
    request(`/api/drill?session_id=${encodeURIComponent(sessionId)}`),
  levels: () => request("/api/course?action=levels"),
  courseLevel: (level) => request(`/api/course?level=${encodeURIComponent(level)}`),
  startCourse: (level) =>
    request("/api/course?action=start", { method: "POST", body: JSON.stringify({ level }) }),
  courseQueue: (level, mode) =>
    request(`/api/course?action=queue&level=${encodeURIComponent(level)}&mode=${encodeURIComponent(mode)}`),
  sky: () => request("/api/course?action=sky"),
  daily: (summary = false) => request(`/api/course?action=daily${summary ? "&summary=1" : ""}`),
  courseAnswer: (body) =>
    request("/api/course?action=answer", { method: "POST", body: JSON.stringify(body) }),
  inspect: (subjectId) =>
    request(`/api/inspect?subject_id=${encodeURIComponent(subjectId)}`),
};
