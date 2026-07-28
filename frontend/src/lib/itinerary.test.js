import {
  dayKeyAtTimezone,
  findActivityOverlaps,
  groupActivitiesByDay,
  reunionDayCountFromEvent,
  runOfShow,
  zonedDateTimeToEpoch,
} from "./itinerary";

const event = {
  start_at: "2027-07-18T09:00:00",
  end_at: "2027-07-20T18:00:00",
  timezone: "America/New_York",
  agenda: [
    {
      id: "welcome",
      title: "Welcome",
      start_at: "2027-07-18T20:00:00",
      end_at: "2027-07-19T00:30:00",
      visibility: "published",
    },
    {
      id: "dance",
      title: "Dance",
      start_at: "2027-07-18T22:00:00",
      end_at: "2027-07-19T01:00:00",
      visibility: "published",
    },
    {
      id: "breakfast",
      title: "Breakfast",
      start_at: "2027-07-19T08:00:00",
      end_at: "2027-07-19T09:00:00",
      visibility: "published",
    },
  ],
};

test("groups a multiday itinerary and allows activities crossing midnight", () => {
  const groups = groupActivitiesByDay(event);
  expect(Object.keys(groups)).toEqual(["2027-07-18", "2027-07-19"]);
  expect(groups["2027-07-18"]).toHaveLength(2);
  expect(reunionDayCountFromEvent(event)).toBe(3);
});
test("warns about overlaps without removing either activity", () => {
  expect(findActivityOverlaps(event)).toEqual([["welcome", "dance"]]);
  expect(event.agenda).toHaveLength(3);
});

test("classifies happening, up next, and future activities in reunion time", () => {
  const now = new Date(zonedDateTimeToEpoch("2027-07-18T21:00:00", "America/New_York"));
  const rolling = runOfShow(event, now);
  expect(rolling.map((activity) => activity.run_state)).toEqual([
    "happening",
    "up-next",
    "future",
  ]);
});

test("resolves local times across a daylight-saving boundary", () => {
  const before = zonedDateTimeToEpoch("2027-03-14T01:30:00", "America/New_York");
  const after = zonedDateTimeToEpoch("2027-03-14T03:30:00", "America/New_York");
  expect((after - before) / 3_600_000).toBe(1);
});

test("rejects nonexistent and ambiguous wall times without an explicit offset", () => {
  expect(zonedDateTimeToEpoch(
    "2027-03-14T02:30:00",
    "America/New_York"
  )).toBeNaN();
  expect(zonedDateTimeToEpoch(
    "2027-11-07T01:30:00",
    "America/New_York"
  )).toBeNaN();
  expect(zonedDateTimeToEpoch(
    "2027-11-07T01:30:00-05:00",
    "America/New_York"
  )).not.toBeNaN();
});

test("derives day keys from the activity instant and intended timezone", () => {
  expect(dayKeyAtTimezone(
    "2027-07-19T01:00:00Z",
    "America/New_York"
  )).toBe("2027-07-18");
  const offsetEvent = {
    ...event,
    agenda: [{
      id: "late",
      title: "Late gathering",
      start_at: "2027-07-19T01:00:00Z",
      end_at: "2027-07-19T02:00:00Z",
      visibility: "published",
    }],
  };
  expect(Object.keys(groupActivitiesByDay(offsetEvent))).toEqual(["2027-07-18"]);
});
