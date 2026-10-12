import { privateInvitationDestination } from "./privateInvitationDestination";

test.each(["heykindred.org", "www.heykindred.org"])("opens a private RSVP fragment from %s", host => {
  expect(privateInvitationDestination(`https://${host}/rsvp#synthetic-token`)).toBe("/rsvp#synthetic-token");
});
test("moves legacy RSVP tokens out of request paths", () => {
  expect(privateInvitationDestination("https://heykindred.org/rsvp/synthetic-token")).toBe("/rsvp#synthetic-token");
});
test("keeps family invitation access on its existing guarded route", () => {
  expect(privateInvitationDestination("https://heykindred.org/invite/synthetic-code")).toBe("/invite/synthetic-code");
});
test.each(["https://evil.invalid/rsvp#token", "https://heykindred.org.evil.invalid/rsvp#token", "javascript:alert(1)", "https://user:pass@heykindred.org/rsvp#token", "http://heykindred.org/rsvp#token", "https://heykindred.org/rsvp", "https://heykindred.org/home", "https://heykindred.org:444/rsvp#token"])("rejects invalid or external input without exposing it: %s", value => {
  expect(privateInvitationDestination(value)).toBeNull();
});
