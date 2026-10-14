import { describe, it, expect } from "vitest";
import { createGame, validateSave, act, choose } from "./game";
import { endingFor } from "./catalogs";

describe("engine import boundary and action purity", () => {
  it("rejects malicious nested JSON without throwing", () => {
    const state = createGame(37);
    for (const field of [
      "history",
      "relationships",
      "stats",
      "flags",
    ] as const) {
      for (const value of [
        null,
        [null],
        ...(field === "flags" ? [] : [{}]),
        "bad",
        42,
      ]) {
        const input = { ...state, [field]: value };
        expect(() => validateSave(input)).not.toThrow();
        expect(validateSave(input)).toBe(false);
      }
    }
    expect(
      validateSave({ ...state, flags: JSON.parse('{"__proto__":4}') }),
    ).toBe(false);
  });
  it("keeps original save unchanged during action", () => {
    const state = createGame(15),
      before = JSON.stringify(state);
    const next = act(state, { type: "study" });
    expect(JSON.stringify(state)).toBe(before);
    expect(next.age).toBe(1);
    expect(next.stats.intellect).toBeGreaterThan(state.stats.intellect);
    expect(validateSave(next)).toBe(true);
  });
});

describe("long-term economy", () => {
  it("allows a wealthy business career without free repeat purchases", () => {
    let state = createGame(120);
    state.age = state.turn = 18;
    state.stats.intellect = 90;
    state.stats.charisma = 85;
    state = act(state, { type: "job", id: "director" });
    const portfolio = ["shawarma", "startup", "factory", "holding", "empire"];
    for (let i = 0; i < 65 && !state.dead; i++) {
      const id = portfolio.find((id) => !state.properties.includes(id));
      const bought = id ? act(state, { type: "buy", id }) : state;
      state = bought === state ? act(state, { type: "rest" }) : bought;
    }
    expect(state.properties).toContain("empire");
    expect(state.money).toBeGreaterThan(1e9);
    expect(validateSave(state)).toBe(true);
  });
});

describe("save gameplay consistency", () => {
  it("rejects impossible death and invalid random state", () => {
    const state = createGame(88);
    expect(validateSave({ ...state, dead: true, ending: "ending-19" })).toBe(
      false,
    );
    for (const key of ["seed", "rng"])
      for (const value of [-1, 1.5, 4294967296])
        expect(validateSave({ ...state, [key]: value })).toBe(false);
    expect(validateSave(createGame(-1))).toBe(true);
  });
  it("rejects already resolved current events and invalid relationship roles", () => {
    const state = createGame(12);
    expect(validateSave({ ...state, seen: [state.currentEvent] })).toBe(false);
    const bad = structuredClone(state);
    bad.relationships[0].role = "minister";
    expect(validateSave(bad)).toBe(false);
  });
});

describe("story endings affect life endings", () => {
  it("recognizes an earned pigeon crown", () => {
    let s = createGame(12);
    s.age = s.turn = 36;
    s.currentEvent = "chain-pigeon-3";
    s.flags = { chain_pigeon_2: 1 };
    s = choose(s, 0);
    expect(s.flags.ending_pigeon_0).toBe(1);
    expect(endingFor(s)).toBe("ending-1");
  });
});
