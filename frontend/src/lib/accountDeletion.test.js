import { requiresPasswordForAccountDeletion } from "./accountDeletion";

test("password accounts must confirm deletion with their password", () => {
  expect(requiresPasswordForAccountDeletion("password")).toBe(true);
  expect(requiresPasswordForAccountDeletion(undefined)).toBe(true);
});

test("Apple and Google accounts follow the backend passwordless deletion contract", () => {
  expect(requiresPasswordForAccountDeletion("apple")).toBe(false);
  expect(requiresPasswordForAccountDeletion("google")).toBe(false);
});
