const localParts = (value) => {
  const match = String(value || "").match(
    /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?/
  );
  if (!match) return null;
  return {
    year: Number(match[1]),
    month: Number(match[2]),
    day: Number(match[3]),
    hour: Number(match[4]),
    minute: Number(match[5]),
    second: Number(match[6] || 0),
  };
};

const partsAtEpoch = (epoch, timezone) => {
  const formatter = new Intl.DateTimeFormat("en-CA", {
    timeZone: timezone || "UTC",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  });
  return Object.fromEntries(
    formatter.formatToParts(new Date(epoch))
      .filter((part) => part.type !== "literal")
      .map((part) => [part.type, Number(part.value)])
  );
};

export function zonedDateTimeToEpoch(value, timezone = "UTC") {
  if (!value) return Number.NaN;
  if (/Z$|[+-]\d{2}:\d{2}$/.test(value)) return new Date(value).getTime();
  const desired = localParts(value);
  if (!desired) return Number.NaN;
  const targetAsUtc = Date.UTC(
    desired.year,
    desired.month - 1,
    desired.day,
    desired.hour,
    desired.minute,
    desired.second
  );
  let guess = targetAsUtc;
  try {
    for (let iteration = 0; iteration < 3; iteration += 1) {
      const actual = partsAtEpoch(guess, timezone);
      const actualAsUtc = Date.UTC(
        actual.year,
        actual.month - 1,
        actual.day,
        actual.hour,
        actual.minute,
        actual.second
      );
      const correction = targetAsUtc - actualAsUtc;
      guess += correction;
      if (correction === 0) break;
    }
    return guess;
  } catch {
    return new Date(value).getTime();
  }
}
export function structuredActivities(event) {
  return (event?.agenda || [])
    .filter((activity) => activity.start_at && activity.visibility !== "archived")
    .sort((left, right) => {
      const leftTime = zonedDateTimeToEpoch(
        left.start_at,
        left.timezone || event?.timezone || "UTC"
      );
      const rightTime = zonedDateTimeToEpoch(
        right.start_at,
        right.timezone || event?.timezone || "UTC"
      );
      return leftTime - rightTime;
    });
}

export function groupActivitiesByDay(event, { publishedOnly = false } = {}) {
  return structuredActivities(event).reduce((groups, activity) => {
    if (publishedOnly && activity.visibility !== "published") return groups;
    const day = activity.start_at.slice(0, 10);
    if (!groups[day]) groups[day] = [];
    groups[day].push(activity);
    return groups;
  }, {});
}

export function findActivityOverlaps(event) {
  const activities = structuredActivities(event);
  const overlaps = [];
  activities.forEach((left, index) => {
    const leftStart = zonedDateTimeToEpoch(left.start_at, left.timezone || event.timezone);
    const leftEnd = zonedDateTimeToEpoch(left.end_at, left.timezone || event.timezone);
    activities.slice(index + 1).forEach((right) => {
      const rightStart = zonedDateTimeToEpoch(right.start_at, right.timezone || event.timezone);
      const rightEnd = zonedDateTimeToEpoch(right.end_at, right.timezone || event.timezone);
      if (leftStart < rightEnd && rightStart < leftEnd) {
        overlaps.push([left.id, right.id]);
      }
    });
  });
  return overlaps;
}

export function runOfShow(event, now = new Date()) {
  const activities = structuredActivities(event).filter(
    (activity) => activity.visibility === "published"
  );
  const nowEpoch = now.getTime();
  let nextAssigned = false;
  return activities.map((activity) => {
    const timezone = activity.timezone || event?.timezone || "UTC";
    const start = zonedDateTimeToEpoch(activity.start_at, timezone);
    const end = zonedDateTimeToEpoch(activity.end_at, timezone);
    let state = "future";
    if (end < nowEpoch) state = "past";
    else if (start <= nowEpoch && nowEpoch <= end) state = "happening";
    else if (!nextAssigned && start > nowEpoch) {
      state = "up-next";
      nextAssigned = true;
    } else {
      const today = partsAtEpoch(nowEpoch, event?.timezone || "UTC");
      const activityDay = localParts(activity.start_at);
      state = activityDay
        && today.year === activityDay.year
        && today.month === activityDay.month
        && today.day === activityDay.day
        ? "later-today"
        : "future";
    }
    return { ...activity, run_state: state };
  });
}

export function reunionDayCountFromEvent(event) {
  const start = String(event?.start_at || "").slice(0, 10);
  const end = String(event?.end_at || event?.start_at || "").slice(0, 10);
  if (!start) return 0;
  const startEpoch = Date.parse(`${start}T12:00:00Z`);
  const endEpoch = Date.parse(`${end || start}T12:00:00Z`);
  if (Number.isNaN(startEpoch) || Number.isNaN(endEpoch) || endEpoch < startEpoch) return 1;
  return Math.floor((endEpoch - startEpoch) / 86_400_000) + 1;
}
