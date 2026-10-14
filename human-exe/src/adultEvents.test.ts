import { describe, it, expect } from "vitest";
import { ADULT_EVENTS } from "./adultEvents";
import { createGame, choose, selectEvent, act } from "./game";
import { EVENTS } from "./events";
describe("adult relationship boundaries", () => {
  it("intimacy action costs a year and is unavailable to children or family-only relationships", () => {
    const child = createGame(9);
    expect(act(child, { type: "intimacy" })).toBe(child);
    child.age = child.turn = 18;
    expect(act(child, { type: "intimacy" })).toBe(child);
    child.relationships.push({
      name: "Лера",
      role: "партнёр",
      bond: 75,
      memory: [],
    });
    const next = act(child, { type: "intimacy" });
    expect(next.age).toBe(19);
    expect(next.flags.intimacy).toBe(1);
    expect(next.relationships[1].memory[0]).toContain("по взаимному согласию");
  });
  it("gates all adult scenes to 18+ and requires a romantic partner for intimacy", () => {
    expect(ADULT_EVENTS.every((e) => e.minAge === 18)).toBe(true);
    const s = createGame(44);
    s.age = s.turn = 18;
    s.currentEvent = "adult-consent";
    expect(choose(s, 0)).toBe(s);
    s.currentEvent = "";
    s.seen = EVENTS.filter((e) => e.id !== "adult-consent").map((e) => e.id);
    expect(selectEvent(s).id).toBe("ordinary");
  });
  it("records consent and applies intimacy to the partner rather than family", () => {
    const s = createGame(44);
    s.age = s.turn = 25;
    s.currentEvent = "adult-consent";
    s.stats.stress = 30;
    s.relationships.unshift({
      name: "Лера",
      role: "партнёр",
      bond: 75,
      memory: [],
    });
    const next = choose(s, 0);
    expect(next.flags.intimacy).toBe(1);
    expect(next.relationships[0].bond).toBe(83);
    expect(next.relationships[1].bond).toBe(s.relationships[1].bond);
    expect(next.relationships[0].memory[0]).toContain("Оба согласились");
  });
  it("respects refusal without recording intimacy", () => {
    const s = createGame(44);
    s.age = s.turn = 25;
    s.currentEvent = "adult-consent";
    s.relationships.push({
      name: "Лера",
      role: "партнёр",
      bond: 75,
      memory: [],
    });
    const next = choose(s, 2);
    expect(next.flags.intimacy).toBeUndefined();
    expect(next.relationships[1].bond).toBe(79);
  });
});
