const PASSWORDLESS_ACCOUNT_PROVIDERS = new Set(["apple", "google"]);

export const requiresPasswordForAccountDeletion = (authProvider) =>
  !PASSWORDLESS_ACCOUNT_PROVIDERS.has(String(authProvider || "").toLowerCase());
