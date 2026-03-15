import { useCallback, useEffect, useState } from "react";
import { BarChart3, CheckCircle2, Circle, Lock, PlusCircle, Trash2, Vote } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { apiRequest, formatDateTime } from "@/lib/api";
import { toast } from "@/components/ui/sonner";

const initialForm = { title: "", description: "", options: ["", ""], allow_multiple: false, closes_at: "" };

export const PollsPage = ({ token, user }) => {
  const [polls, setPolls] = useState([]);
  const [form, setForm] = useState(initialForm);
  const [isCreating, setIsCreating] = useState(false);
  const [showForm, setShowForm] = useState(false);

  const canCreate = user?.role === "host" || user?.role === "organizer";

  const loadPolls = useCallback(async () => {
    try {
      const payload = await apiRequest("/polls", { token });
      setPolls(payload.polls || []);
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to load polls.");
    }
  }, [token]);

  useEffect(() => { loadPolls(); }, [loadPolls]);

  const handleCreate = async (e) => {
    e.preventDefault();
    const validOptions = form.options.filter((o) => o.trim());
    if (validOptions.length < 2) {
      toast.error("At least 2 options are required.");
      return;
    }
    setIsCreating(true);
    try {
      await apiRequest("/polls", {
        method: "POST",
        token,
        data: {
          title: form.title,
          description: form.description,
          options: validOptions.map((text) => ({ text })),
          allow_multiple: form.allow_multiple,
          closes_at: form.closes_at,
        },
      });
      toast.success("Poll created.");
      setForm(initialForm);
      setShowForm(false);
      loadPolls();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to create poll.");
    } finally {
      setIsCreating(false);
    }
  };

  const handleVote = async (pollId, optionId) => {
    try {
      await apiRequest(`/polls/${pollId}/vote`, {
        method: "POST",
        token,
        data: { option_ids: [optionId] },
      });
      toast.success("Vote recorded.");
      loadPolls();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to vote.");
    }
  };

  const handleClose = async (pollId) => {
    try {
      await apiRequest(`/polls/${pollId}/close`, { method: "POST", token });
      toast.success("Poll closed.");
      loadPolls();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to close poll.");
    }
  };

  const handleDelete = async (pollId) => {
    try {
      await apiRequest(`/polls/${pollId}`, { method: "DELETE", token });
      toast.success("Poll deleted.");
      loadPolls();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to delete poll.");
    }
  };

  const addOption = () => {
    if (form.options.length < 10) {
      setForm((f) => ({ ...f, options: [...f.options, ""] }));
    }
  };

  const removeOption = (index) => {
    if (form.options.length > 2) {
      setForm((f) => ({ ...f, options: f.options.filter((_, i) => i !== index) }));
    }
  };

  const updateOption = (index, value) => {
    setForm((f) => ({
      ...f,
      options: f.options.map((o, i) => (i === index ? value : o)),
    }));
  };

  return (
    <div className="space-y-6" data-testid="polls-page">
      <section className="archival-card">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="flex items-center gap-3">
              <Vote className="h-5 w-5 text-primary" />
              <p className="eyebrow-text">Community decisions</p>
            </div>
            <h2 className="mt-3 font-display text-3xl text-foreground sm:text-4xl" data-testid="polls-page-title">
              Polls & Voting
            </h2>
            <p className="mt-2 max-w-2xl text-sm leading-7 text-muted-foreground">
              Make collective decisions with transparency. Create polls, cast votes, and see what your circle thinks.
            </p>
          </div>
          {canCreate && (
            <Button
              className="rounded-full self-start"
              data-testid="polls-create-toggle-button"
              onClick={() => setShowForm(!showForm)}
              variant={showForm ? "secondary" : "default"}
            >
              <PlusCircle className="mr-2 h-4 w-4" />
              {showForm ? "Cancel" : "New poll"}
            </Button>
          )}
        </div>
      </section>

      {showForm && (
        <section className="archival-card" data-testid="polls-create-form">
          <p className="eyebrow-text">Create a new poll</p>
          <form className="mt-4 space-y-4" onSubmit={handleCreate}>
            <label>
              <span className="field-label">Question</span>
              <Input
                className="field-input"
                data-testid="polls-title-input"
                onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
                placeholder="What should we decide?"
                required
                value={form.title}
              />
            </label>
            <label>
              <span className="field-label">Description (optional)</span>
              <Textarea
                className="field-textarea"
                data-testid="polls-description-input"
                onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
                placeholder="Add context for voters..."
                value={form.description}
              />
            </label>

            <div>
              <span className="field-label">Options</span>
              <div className="mt-2 space-y-2">
                {form.options.map((opt, index) => (
                  <div className="flex items-center gap-2" key={index}>
                    <Input
                      className="field-input flex-1"
                      data-testid={`polls-option-input-${index}`}
                      onChange={(e) => updateOption(index, e.target.value)}
                      placeholder={`Option ${index + 1}`}
                      required
                      value={opt}
                    />
                    {form.options.length > 2 && (
                      <Button
                        className="h-9 w-9 rounded-full p-0"
                        data-testid={`polls-option-remove-${index}`}
                        onClick={() => removeOption(index)}
                        type="button"
                        variant="ghost"
                      >
                        <Trash2 className="h-3.5 w-3.5 text-muted-foreground" />
                      </Button>
                    )}
                  </div>
                ))}
              </div>
              {form.options.length < 10 && (
                <Button
                  className="mt-2 rounded-full"
                  data-testid="polls-add-option-button"
                  onClick={addOption}
                  size="sm"
                  type="button"
                  variant="ghost"
                >
                  <PlusCircle className="mr-1 h-3.5 w-3.5" /> Add option
                </Button>
              )}
            </div>

            <label className="flex items-center gap-3">
              <input
                checked={form.allow_multiple}
                data-testid="polls-allow-multiple-checkbox"
                onChange={(e) => setForm((f) => ({ ...f, allow_multiple: e.target.checked }))}
                type="checkbox"
              />
              <span className="text-sm text-foreground">Allow multiple selections</span>
            </label>

            <Button
              className="rounded-full"
              data-testid="polls-submit-button"
              disabled={isCreating}
              type="submit"
            >
              {isCreating ? "Creating..." : "Create poll"}
            </Button>
          </form>
        </section>
      )}

      {polls.length === 0 && !showForm ? (
        <section className="archival-card text-center" data-testid="polls-empty-state">
          <BarChart3 className="mx-auto h-10 w-10 text-muted-foreground/30" />
          <p className="mt-3 text-sm text-muted-foreground">
            No polls yet. {canCreate ? "Create one to start a community decision." : "Check back when your circle starts a vote."}
          </p>
        </section>
      ) : (
        <div className="grid gap-6 lg:grid-cols-2">
          {polls.map((poll) => (
            <PollCard
              canManage={canCreate}
              key={poll.id}
              onClose={handleClose}
              onDelete={handleDelete}
              onVote={handleVote}
              poll={poll}
            />
          ))}
        </div>
      )}
    </div>
  );
};

const PollCard = ({ poll, onVote, onClose, onDelete, canManage }) => {
  const maxVotes = Math.max(...poll.options.map((o) => o.vote_count), 1);

  return (
    <article className="archival-card" data-testid={`poll-card-${poll.id}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1">
          <div className="flex items-center gap-2">
            {!poll.is_active && <Lock className="h-3.5 w-3.5 text-muted-foreground" />}
            <h3 className="font-display text-xl text-foreground" data-testid={`poll-title-${poll.id}`}>
              {poll.title}
            </h3>
          </div>
          {poll.description && (
            <p className="mt-1 text-sm text-muted-foreground">{poll.description}</p>
          )}
        </div>
        <span
          className={`rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider ${
            poll.is_active
              ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300"
              : "bg-muted text-muted-foreground"
          }`}
          data-testid={`poll-status-${poll.id}`}
        >
          {poll.is_active ? "Active" : "Closed"}
        </span>
      </div>

      <div className="mt-4 space-y-2">
        {poll.options.map((option) => {
          const pct = poll.total_votes > 0 ? Math.round((option.vote_count / poll.total_votes) * 100) : 0;
          return (
            <button
              className={`relative w-full overflow-hidden rounded-xl border px-4 py-3 text-left transition-all duration-300 ${
                option.voted_by_me
                  ? "border-primary/40 bg-primary/[0.06]"
                  : "border-border/60 bg-background/50 hover:border-primary/20"
              } ${!poll.is_active ? "pointer-events-none opacity-80" : ""}`}
              data-testid={`poll-option-${option.id}`}
              disabled={!poll.is_active}
              key={option.id}
              onClick={() => onVote(poll.id, option.id)}
            >
              <div
                className="absolute inset-y-0 left-0 bg-primary/[0.08] transition-all duration-500"
                style={{ width: `${pct}%` }}
              />
              <div className="relative flex items-center justify-between gap-3">
                <div className="flex items-center gap-2.5">
                  {option.voted_by_me ? (
                    <CheckCircle2 className="h-4 w-4 flex-shrink-0 text-primary" />
                  ) : (
                    <Circle className="h-4 w-4 flex-shrink-0 text-muted-foreground/50" />
                  )}
                  <span className="text-sm font-medium text-foreground">{option.text}</span>
                </div>
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <span className="font-mono">{pct}%</span>
                  <span>({option.vote_count})</span>
                </div>
              </div>
            </button>
          );
        })}
      </div>

      <div className="mt-4 flex items-center justify-between text-xs text-muted-foreground">
        <div className="flex items-center gap-3">
          <span>{poll.total_votes} vote{poll.total_votes !== 1 ? "s" : ""}</span>
          <span>by {poll.created_by_name}</span>
          {poll.allow_multiple && <span className="rounded-full bg-muted px-2 py-0.5 text-[10px]">Multi-select</span>}
        </div>
        <span>{formatDateTime(poll.created_at)}</span>
      </div>

      {canManage && (
        <div className="mt-3 flex gap-2 border-t border-border/30 pt-3">
          {poll.is_active && (
            <Button
              className="rounded-full"
              data-testid={`poll-close-${poll.id}`}
              onClick={() => onClose(poll.id)}
              size="sm"
              variant="secondary"
            >
              <Lock className="mr-1 h-3 w-3" /> Close poll
            </Button>
          )}
          <Button
            className="rounded-full"
            data-testid={`poll-delete-${poll.id}`}
            onClick={() => onDelete(poll.id)}
            size="sm"
            variant="ghost"
          >
            <Trash2 className="mr-1 h-3 w-3" /> Delete
          </Button>
        </div>
      )}
    </article>
  );
};
