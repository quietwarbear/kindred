const CLAIM_KEY = "kindred:guest-family-access-claim";
const OPERATION_KEY = "kindred:guest-family-access-operation";

export const saveGuestFamilyClaim = (claim) => {
  if (claim) window.sessionStorage.setItem(CLAIM_KEY, claim);
};

export const loadGuestFamilyClaim = () => window.sessionStorage.getItem(CLAIM_KEY) || "";

export const clearGuestFamilyClaim = () => window.sessionStorage.removeItem(CLAIM_KEY);

export const familyAccessOperationKey = () => {
  const existing = window.sessionStorage.getItem(OPERATION_KEY);
  if (existing) return existing;
  const random = window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
  const value = `family-access:${random}`;
  window.sessionStorage.setItem(OPERATION_KEY, value);
  return value;
};

export const clearFamilyAccessOperation = () => window.sessionStorage.removeItem(OPERATION_KEY);
