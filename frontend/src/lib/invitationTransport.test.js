import {
  fragmentInvitationUrl,
  invitationAuthorization,
  invitationTokenFromLocation,
} from "./invitationTransport";

test("puts invitation credentials in the fragment instead of the request URL", () => {
  const url = fragmentInvitationUrl("https://heykindred.org", "private/token value");
  expect(url).toBe("https://heykindred.org/rsvp#private%2Ftoken%20value");
  expect(new URL(url).pathname).toBe("/rsvp");
  expect(new URL(url).search).toBe("");
});

test("reads fragments first and supports legacy route transition", () => {
  expect(invitationTokenFromLocation({ hash: "#fragment-token" }, "legacy-token"))
    .toBe("fragment-token");
  expect(invitationTokenFromLocation({ hash: "" }, "legacy-token"))
    .toBe("legacy-token");
});

test("transports invitation credentials in an authorization header", () => {
  expect(invitationAuthorization("private-token")).toEqual({
    Authorization: "Bearer private-token",
  });
});
