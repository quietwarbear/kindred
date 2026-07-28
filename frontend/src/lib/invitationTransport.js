export const invitationTokenFromLocation = (location, legacyToken = "") => {
  const fragment = String(location?.hash || "").replace(/^#/, "");
  if (fragment) {
    try {
      return decodeURIComponent(fragment);
    } catch {
      return fragment;
    }
  }
  return legacyToken || "";
};

export const fragmentInvitationUrl = (origin, invitationId) => (
  `${origin}/rsvp#${encodeURIComponent(invitationId)}`
);

export const invitationAuthorization = (token) => ({
  Authorization: `Bearer ${token}`,
});
