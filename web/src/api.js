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
  me: () => request("/api/me"),
  login: (password) =>
    request("/api/login", { method: "POST", body: JSON.stringify({ password }) }),
  logout: () => request("/api/logout", { method: "POST", body: "{}" }),
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
};
