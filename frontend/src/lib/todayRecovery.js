// Keep authorization/unavailable responses out of the network-retry loop.
// Never echo server details or private account information into the screen.
export const todayFailure = (error) => {
  const status = error?.response?.status;
  if (status === 404 || status === 403) return { kind: "unavailable" };
  if (status === 401) return { kind: "session" };
  return { kind: "temporary" };
};
