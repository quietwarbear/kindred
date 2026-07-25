export const PUBLIC_IDENTITY = Object.freeze({
  productName: "Kindred",
  companyName: "Ubuntu Market LLC",
  canonicalOrigin: "https://www.heykindred.org",
  canonicalHost: "heykindred.org",
  supportEmail: "support@ubuntu-village.org",
});

export const publicUrl = (path = "/") =>
  `${PUBLIC_IDENTITY.canonicalOrigin}${path.startsWith("/") ? path : `/${path}`}`;
