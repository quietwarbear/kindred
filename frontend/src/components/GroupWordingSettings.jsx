import { useEffect, useState } from "react";
import { Users } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "@/components/ui/sonner";
import { apiRequest, errorDetail } from "@/lib/api";
import {
  CUSTOM_GROUP_PRESET,
  GROUP_PRESETS,
  GROUP_PRESET_KEYS,
  MAX_GROUP_LABEL_LENGTH,
  groupWords,
  useGroupWording,
  validateGroupLabel,
} from "@/lib/groupWording";

// K3: organizers choose the word this space uses for its people. Members never
// see this card; the server refuses the change for them as well.
export const GroupWordingSettings = ({ token, user, onSessionRefresh }) => {
  const current = useGroupWording();
  const [preset, setPreset] = useState(current.preset);
  const [singular, setSingular] = useState(current.preset === CUSTOM_GROUP_PRESET ? current.label.singular : "");
  const [plural, setPlural] = useState(current.preset === CUSTOM_GROUP_PRESET ? current.label.plural : "");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setPreset(current.preset);
    if (current.preset === CUSTOM_GROUP_PRESET) {
      setSingular(current.label.singular);
      setPlural(current.label.plural);
    }
  }, [current]);

  if (!["host", "organizer"].includes(user?.role)) return null;

  const choice = validateGroupLabel({ preset, singular, plural });
  const preview = groupWords(choice.ok ? choice.label : current.label);
  const unchanged = choice.ok && JSON.stringify(choice.label) === JSON.stringify(current.label);
  const showError = preset === CUSTOM_GROUP_PRESET && (singular || plural) && !choice.ok;

  const save = async (event) => {
    event.preventDefault();
    if (!choice.ok) return;
    setSaving(true);
    try {
      await apiRequest("/community/group-label", { method: "PUT", token, data: choice.label });
      await onSessionRefresh?.();
      toast.success(`This space now says “${groupWords(choice.label).noun}”.`);
    } catch (error) {
      toast.error(errorDetail(error, "The wording could not be saved."));
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="archival-card" data-testid="settings-group-wording-card">
      <div className="flex items-start gap-3">
        <Users className="mt-1 h-5 w-5 text-primary" />
        <div>
          <p className="eyebrow-text">Wording</p>
          <h2 className="mt-2 font-display text-3xl text-foreground">What do your people call themselves?</h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
            Kindred uses this word across invitations, Today, reminders and the memory capsule for everyone in this space. Plan names don’t change.
          </p>
        </div>
      </div>
      <form className="mt-5 space-y-4" onSubmit={save}>
        <fieldset className="flex flex-wrap gap-2" data-testid="group-wording-options">
          <legend className="sr-only">Group word</legend>
          {[...GROUP_PRESET_KEYS, CUSTOM_GROUP_PRESET].map((key) => (
            <label
              className={`cursor-pointer rounded-full border px-4 py-2 text-sm font-semibold transition ${preset === key ? "border-primary bg-primary text-primary-foreground" : "border-border bg-background/70 text-foreground"}`}
              key={key}
            >
              <input
                checked={preset === key}
                className="sr-only"
                data-testid={`group-wording-option-${key}`}
                name="group-wording"
                onChange={() => setPreset(key)}
                type="radio"
                value={key}
              />
              {key === CUSTOM_GROUP_PRESET ? "Something else" : GROUP_PRESETS[key].singular.charAt(0).toUpperCase() + GROUP_PRESETS[key].singular.slice(1)}
            </label>
          ))}
        </fieldset>
        {preset === CUSTOM_GROUP_PRESET ? (
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="text-sm font-semibold" htmlFor="group-wording-singular">
              One
              <Input
                className="mt-2"
                data-testid="group-wording-singular"
                id="group-wording-singular"
                maxLength={MAX_GROUP_LABEL_LENGTH}
                onChange={(event) => setSingular(event.target.value)}
                placeholder="e.g. village"
                value={singular}
              />
            </label>
            <label className="text-sm font-semibold" htmlFor="group-wording-plural">
              More than one
              <Input
                className="mt-2"
                data-testid="group-wording-plural"
                id="group-wording-plural"
                maxLength={MAX_GROUP_LABEL_LENGTH}
                onChange={(event) => setPlural(event.target.value)}
                placeholder="e.g. villages"
                value={plural}
              />
            </label>
          </div>
        ) : null}
        {showError ? <p className="text-sm text-destructive" role="alert">{choice.error}</p> : null}
        <p className="text-sm text-muted-foreground" data-testid="group-wording-preview">
          Preview: “{preview.fill("Welcome to your {group} space")}” · “{preview.fill("{Group} Today")}”
        </p>
        <Button data-testid="group-wording-save" disabled={saving || !choice.ok || unchanged} type="submit">
          {saving ? "Saving…" : "Save wording"}
        </Button>
      </form>
    </section>
  );
};
