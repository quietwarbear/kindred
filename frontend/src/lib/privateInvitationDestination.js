export const privateInvitationDestination = (value) => {
  try {
    const url = new URL(String(value || "").trim());
    if (url.protocol !== "https:" || url.username || url.password || url.port || !["heykindred.org", "www.heykindred.org"].includes(url.hostname)) return null;
    if (url.pathname === "/rsvp" && url.hash.length > 1) return `/rsvp${url.hash}`;
    const rsvp = url.pathname.match(/^\/rsvp\/([^/]+)$/);
    if (rsvp) return `/rsvp#${encodeURIComponent(decodeURIComponent(rsvp[1]))}`;
    if (/^\/invite\/[^/]+$/.test(url.pathname)) return url.pathname;
    return null;
  } catch { return null; }
};
