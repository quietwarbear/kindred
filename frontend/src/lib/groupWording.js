// Organizer-chosen group wording (K3).
//
// Kindred says "family" by default. An organizer can choose the word their
// people use instead — community, congregation, circle, team, or a custom
// singular + plural — and every screen inside a space reads it from here.
// The backend mirror is backend/group_wording.py; presets, the length cap and
// the allowed characters must stay identical in both.
//
// Usage inside a component:
//   const words = useGroupWording();
//   words.noun        -> "family"        words.Noun        -> "Family"
//   words.nouns       -> "families"      words.Nouns       -> "Families"
//   words.possessive  -> "family's"      words.Possessive  -> "Family's"
//   words.fill("Invite the {group}")    -> "Invite the family"
//   tokens: {group} {Group} {groups} {Groups} {group's} {Group's}
//
// The app has no locale files today; if it gains them, translate around these
// tokens rather than around the word itself.
//
// Marketing pages, plan names and the brand line do not use this.

import { createContext, createElement, useContext, useMemo } from "react";

export const GROUP_PRESETS = Object.freeze({
  family: { singular: "family", plural: "families" },
  community: { singular: "community", plural: "communities" },
  congregation: { singular: "congregation", plural: "congregations" },
  circle: { singular: "circle", plural: "circles" },
  team: { singular: "team", plural: "teams" },
});
export const GROUP_PRESET_KEYS = Object.freeze(Object.keys(GROUP_PRESETS));
export const DEFAULT_GROUP_PRESET = "family";
export const CUSTOM_GROUP_PRESET = "custom";
export const MAX_GROUP_LABEL_LENGTH = 24;

const LABEL_PATTERN = /^\p{L}+(?:[ '\-’]\p{L}+)*$/u;

export const defaultGroupLabel = () => ({
  preset: DEFAULT_GROUP_PRESET,
  ...GROUP_PRESETS[DEFAULT_GROUP_PRESET],
});

const cleanWord = (value) => String(value ?? "").replace(/\s+/g, " ").trim();

const wordError = (word, field) => {
  if (!word) return `Enter the ${field} word.`;
  if (word.length > MAX_GROUP_LABEL_LENGTH) {
    return `Keep the ${field} word to ${MAX_GROUP_LABEL_LENGTH} characters or fewer.`;
  }
  if (!LABEL_PATTERN.test(word)) {
    return `Use letters only for the ${field} word (spaces, hyphens and apostrophes are fine).`;
  }
  return "";
};

// Returns { ok: true, label } or { ok: false, error }.
export const validateGroupLabel = ({ preset, singular, plural } = {}) => {
  const key = String(preset ?? "").trim().toLowerCase();
  if (GROUP_PRESETS[key]) return { ok: true, label: { preset: key, ...GROUP_PRESETS[key] } };
  if (key !== CUSTOM_GROUP_PRESET) return { ok: false, error: "Choose one of the listed words or a custom one." };
  const one = cleanWord(singular);
  const many = cleanWord(plural);
  const error = wordError(one, "singular") || wordError(many, "plural");
  if (error) return { ok: false, error };
  return { ok: true, label: { preset: CUSTOM_GROUP_PRESET, singular: one, plural: many } };
};

// Anything missing or unreadable resolves to the family preset.
export const resolveGroupLabel = (raw) => {
  if (!raw || typeof raw !== "object") return defaultGroupLabel();
  const result = validateGroupLabel(raw);
  return result.ok ? result.label : defaultGroupLabel();
};

// "Choir" mid-sentence reads "choir"; an all-caps acronym stays as typed.
const lowerFirst = (word) => (word.length > 1 && word.slice(1) === word.slice(1).toLowerCase()
  ? word.charAt(0).toLowerCase() + word.slice(1)
  : word);
const upperFirst = (word) => word.charAt(0).toUpperCase() + word.slice(1);

const TOKEN_PATTERN = /\{(group|Group|groups|Groups|group's|Group's)\}/g;

export const groupWords = (raw) => {
  const label = resolveGroupLabel(raw);
  const noun = lowerFirst(label.singular);
  const nouns = lowerFirst(label.plural);
  const forms = {
    group: noun,
    Group: upperFirst(noun),
    groups: nouns,
    Groups: upperFirst(nouns),
    "group's": `${noun}'s`,
    "Group's": `${upperFirst(noun)}'s`,
  };
  return Object.freeze({
    label,
    preset: label.preset,
    isDefault: label.preset === DEFAULT_GROUP_PRESET,
    noun,
    Noun: forms.Group,
    nouns,
    Nouns: forms.Groups,
    possessive: forms["group's"],
    Possessive: forms["Group's"],
    count: (n) => (Number(n) === 1 ? noun : nouns),
    fill: (template) => String(template ?? "").replace(TOKEN_PATTERN, (_, token) => forms[token]),
  });
};

const DEFAULT_WORDS = groupWords(null);
const GroupWordingContext = createContext(DEFAULT_WORDS);

// `label` is the raw stored value (community.group_label from /auth/me, or the
// group_label a public payload carries). Nested providers override outer ones.
export const GroupWordingProvider = ({ label, children }) => {
  const key = JSON.stringify(label ?? null);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const words = useMemo(() => groupWords(label), [key]);
  return createElement(GroupWordingContext.Provider, { value: words }, children);
};

export const useGroupWording = () => useContext(GroupWordingContext);
