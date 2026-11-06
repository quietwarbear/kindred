import React from "react";
import { createRoot } from "react-dom/client";

import {
  GROUP_PRESET_KEYS,
  GroupWordingProvider,
  MAX_GROUP_LABEL_LENGTH,
  groupWords,
  resolveGroupLabel,
  useGroupWording,
  validateGroupLabel,
} from "./groupWording";

describe("default", () => {
  test.each([undefined, null, "family", 7, {}, { preset: "nonsense" }, { preset: "custom", singular: "<b>", plural: "x" }])(
    "%p resolves to the family preset",
    (raw) => {
      const words = groupWords(raw);
      expect(words.preset).toBe("family");
      expect(words.isDefault).toBe(true);
      expect([words.noun, words.Noun, words.nouns, words.Nouns]).toEqual(["family", "Family", "families", "Families"]);
      expect([words.possessive, words.Possessive]).toEqual(["family's", "Family's"]);
    },
  );

  test("existing copy reads exactly as before", () => {
    const { fill } = groupWords(undefined);
    expect(fill("{Group} Today")).toBe("Family Today");
    expect(fill("Welcome to your {group} space")).toBe("Welcome to your family space");
    expect(fill("Chip in for the {group's} pass")).toBe("Chip in for the family's pass");
    expect(fill("{Groups} and {groups}; {Group's} story")).toBe("Families and families; Family's story");
  });
});

describe("presets", () => {
  test("offer exactly the five listed words", () => {
    expect(GROUP_PRESET_KEYS).toEqual(["family", "community", "congregation", "circle", "team"]);
  });

  test.each([
    ["community", "community", "Communities", "community's"],
    ["congregation", "congregation", "Congregations", "congregation's"],
    ["circle", "circle", "Circles", "circle's"],
    ["team", "team", "Teams", "team's"],
  ])("%s", (preset, noun, Nouns, possessive) => {
    const words = groupWords({ preset });
    expect(words.noun).toBe(noun);
    expect(words.Nouns).toBe(Nouns);
    expect(words.possessive).toBe(possessive);
    expect(words.isDefault).toBe(false);
    // The stored singular/plural of a preset can't be overridden by the client.
    expect(groupWords({ preset, singular: "Ignored", plural: "Ignoreds" }).noun).toBe(noun);
  });
});

describe("custom", () => {
  test("uses the organizer's singular and plural in every form", () => {
    const words = groupWords({ preset: "custom", singular: "Village", plural: "Villages" });
    expect([words.noun, words.Noun, words.nouns, words.Nouns]).toEqual(["village", "Village", "villages", "Villages"]);
    expect(words.possessive).toBe("village's");
    expect(words.fill("Invite the {group}. {Groups} welcome.")).toBe("Invite the village. Villages welcome.");
    expect(words.count(1)).toBe("village");
    expect(words.count(3)).toBe("villages");
  });

  test("keeps an acronym or internal capitals as typed", () => {
    expect(groupWords({ preset: "custom", singular: "YMCA", plural: "YMCAs" }).noun).toBe("YMCA");
  });

  test("accepts letters in any script with spaces, hyphens and apostrophes", () => {
    expect(validateGroupLabel({ preset: "custom", singular: "  study   circle ", plural: "study circles" }))
      .toEqual({ ok: true, label: { preset: "custom", singular: "study circle", plural: "study circles" } });
    expect(validateGroupLabel({ preset: "custom", singular: "ìdílé", plural: "àwọn ìdílé" }).ok).toBe(true);
    expect(validateGroupLabel({ preset: "custom", singular: "kin-group", plural: "o'hana" }).ok).toBe(true);
  });

  test.each([
    [{ singular: "", plural: "crews" }, /singular/],
    [{ singular: "crew", plural: "" }, /plural/],
    [{ singular: "a".repeat(MAX_GROUP_LABEL_LENGTH + 1), plural: "crews" }, /characters or fewer/],
    [{ singular: "crew2", plural: "crews" }, /letters only/],
    [{ singular: "<script>", plural: "crews" }, /letters only/],
    [{ singular: "crew", plural: "crews!" }, /letters only/],
  ])("rejects %p", (input, message) => {
    const result = validateGroupLabel({ preset: "custom", ...input });
    expect(result.ok).toBe(false);
    expect(result.error).toMatch(message);
  });

  test("an invalid stored custom value falls back to family", () => {
    expect(resolveGroupLabel({ preset: "custom", singular: "x".repeat(40), plural: "y" }).preset).toBe("family");
  });
});

describe("provider", () => {
  const Probe = () => {
    const words = useGroupWording();
    return <span>{words.fill("{Group} Today · {groups}")}</span>;
  };

  const renderToText = async (element) => {
    const container = document.createElement("div");
    const root = createRoot(container);
    global.IS_REACT_ACT_ENVIRONMENT = true;
    await React.act(async () => root.render(element));
    const text = container.textContent;
    await React.act(async () => root.unmount());
    return text;
  };

  test("without a provider components read the family default", async () => {
    expect(await renderToText(<Probe />)).toBe("Family Today · families");
  });

  test("the nearest provider wins", async () => {
    expect(await renderToText(
      <GroupWordingProvider label={{ preset: "team" }}>
        <GroupWordingProvider label={{ preset: "congregation" }}><Probe /></GroupWordingProvider>
      </GroupWordingProvider>,
    )).toBe("Congregation Today · congregations");
  });
});
