import { describe, expect, it } from "vitest";
import { createGame, choose, act, validateSave, selectEvent } from "./game";
import {
  ACHIEVEMENTS,
  ENDINGS,
  JOBS,
  PROPERTIES,
  earned,
  endingFor,
} from "./catalogs";
import type { GameState } from "./types";

function adult(seed = 1): GameState {
  const s = createGame(seed);
  s.age = 30;
  s.turn = 30;
  s.money = 100000;
  s.debt = 0;
  s.stats = {
    health: 70,
    intellect: 50,
    charisma: 50,
    luck: 50,
    stress: 50,
    reputation: 50,
  };
  s.flags = {};
  s.properties = [];
  s.relationships = [{ name: "Бабушка", bond: 50, role: "семья", memory: [] }];
  s.job = null;
  s.seen = [];
  return s;
}

describe("character and save invariants", () => {
  it("reproduces a seeded birth and produces different lives for different seeds", () => {
    expect(createGame(42)).toEqual(createGame(42));
    expect(createGame(42)).not.toEqual(createGame(43));
    for (let seed = 1; seed <= 100; seed++) {
      const game = createGame(seed);
      expect(validateSave(game)).toBe(true);
      expect(game.name).toBeTruthy();
      expect(game.city).toBeTruthy();
      expect(game.traits.length).toBeGreaterThan(0);
      expect(game.dead).toBe(false);
      Object.values(game.stats).forEach((n) =>
        expect(n).toBeGreaterThanOrEqual(0),
      );
      Object.values(game.stats).forEach((n) =>
        expect(n).toBeLessThanOrEqual(100),
      );
    }
  });
  it("rejects malformed state and non-finite numeric values", () => {
    const s = createGame(1);
    for (const bad of [
      null,
      {},
      { ...s, money: NaN },
      { ...s, debt: -1 },
      { ...s, age: Infinity },
      { ...s, stats: { ...s.stats, charisma: 101 } },
      { ...s, properties: ["unknown-property"] },
      { ...s, achievements: ["fake"] },
      { ...s, currentEvent: "fake" },
      { ...s, ending: "fake" },
      { ...s, properties: ["sofa", "sofa"] },
      { ...s, history: [null] },
      { ...s, relationships: [null] },
      { ...s, flags: { nested: { value: 1 } } },
    ]) {
      expect(validateSave(bad)).toBe(false);
    }
  });
});

describe("content and ending rules", () => {
  it("ships unique career, property, achievement and ending identities", () => {
    expect(JOBS.length).toBeGreaterThanOrEqual(20);
    expect(ACHIEVEMENTS.length).toBeGreaterThanOrEqual(50);
    expect(ENDINGS.length).toBeGreaterThanOrEqual(20);
    for (const catalog of [JOBS, PROPERTIES, ACHIEVEMENTS, ENDINGS]) {
      expect(new Set(catalog.map((x) => x.id)).size).toBe(catalog.length);
    }
  });
  it("has a distinct, valid witness for every ending", () => {
    const witnesses: ((s: GameState) => void)[] = [
      (s) => {
        s.money = 1e9;
      },
      (s) => {
        s.flags.pigeon = 3;
      },
      (s) => {
        s.job = "politician";
        s.stats.reputation = 70;
      },
      (s) => {
        s.stats.reputation = 90;
      },
      (s) => {
        s.stats.stress = 20;
        s.relationships = [
          { name: "Анна", role: "друг", bond: 90, memory: [] },
        ];
      },
      (s) => {
        s.debt = 2e6;
      },
      (s) => {
        s.stats.health = 1;
        s.money = 0;
      },
      (s) => {
        s.job = "criminal";
      },
      (s) => {
        s.job = "blogger";
      },
      (s) => {
        s.stats.intellect = 95;
      },
      (s) => {
        s.properties = ["shawarma"];
      },
      (s) => {
        s.properties = ["factory"];
      },
      (s) => {
        s.properties = ["cat", "sofa", "garage", "flat"];
      },
      (s) => {
        s.relationships = [
          { name: "Анна", role: "супруг", bond: 60, memory: [] },
        ];
      },
      (s) => {
        s.flags.work = 20;
      },
      (s) => {
        s.flags.rest = 15;
      },
      (s) => {
        s.debt = 100;
      },
      (s) => {
        s.seen = Array.from({ length: 60 }, (_, i) => String(i));
      },
      () => {},
      (s) => {
        s.age = 20;
      },
    ];
    witnesses.forEach((prepare, index) => {
      const s = adult();
      prepare(s);
      expect(endingFor(s)).toBe(ENDINGS[index].id);
    });
  });
  it("awards money and relationship achievements from actual state and does not invent ids", () => {
    const s = adult();
    s.money = 1e9;
    s.relationships = [{ name: "Анна", role: "супруг", bond: 95, memory: [] }];
    const ids = earned(s);
    expect(ids).toEqual(
      expect.arrayContaining([
        "rich",
        "tycoon",
        "billion",
        "friend",
        "married",
      ]),
    );
    expect(ids.every((id) => ACHIEVEMENTS.some((a) => a.id === id))).toBe(true);
  });
});

describe("turns, economy and longevity", () => {
  it("does not mutate the previous life when choosing a valid event option", () => {
    const s = createGame(44);
    const before = structuredClone(s);
    const next = choose(s, 0);
    expect(s).toEqual(before);
    expect(next.turn).toBeGreaterThan(s.turn);
    expect(next.age).toBeGreaterThan(s.age);
    expect(next.history.length).toBeGreaterThan(s.history.length);
    expect(validateSave(next)).toBe(true);
  });
  it("cannot buy the same asset twice or spend money that is unavailable", () => {
    const s = adult();
    s.money = 1_000_000;
    const first = act(s, { type: "buy", id: "sofa" });
    expect(first.properties).toContain("sofa");
    const second = act(first, { type: "buy", id: "sofa" });
    expect(second.properties.filter((id) => id === "sofa")).toHaveLength(1);
    expect(second.money).toBe(first.money);
    const poor = adult();
    poor.money = 0;
    expect(act(poor, { type: "buy", id: "empire" }).properties).not.toContain(
      "empire",
    );
  });
  it("records employment, pays salary, accrues interest and repays debt without negative balances", () => {
    let s = adult();
    s.stats.intellect = 100;
    s.stats.charisma = 100;
    s = act(s, { type: "job", id: "developer" });
    expect(s.job).toBe("developer");
    const cash = s.money;
    s = act(s, { type: "work" });
    expect(s.money).toBeGreaterThan(cash);
    s = act(s, { type: "loan", amount: 50_000 });
    expect(s.debt).toBeGreaterThan(0);
    s = choose(s, 0);
    expect(s.debt).toBeGreaterThanOrEqual(0);
    s.money = 1_000_000;
    s = act(s, { type: "repay", amount: s.debt });
    expect(s.debt).toBe(0);
    expect(s.money).toBeGreaterThanOrEqual(0);
  });
  it("cannot change a completed life", () => {
    const s = adult();
    s.dead = true;
    s.ending = "ending-18";
    s.stats.health = 0;
    expect(choose(s, 0)).toEqual(s);
    expect(act(s, { type: "rest" })).toEqual(s);
  });
  it("terminates random play and preserves valid state across many seeds", () => {
    for (let seed = 1; seed <= 40; seed++) {
      let s = createGame(seed);
      let turns = 0;
      while (!s.dead && turns++ < 500) {
        if (s.age >= 18 && turns % 4 === 0) s = act(s, { type: "rest" });
        s = choose(s, 0);
        expect(validateSave(s), `seed ${seed}, turn ${turns}`).toBe(true);
        expect(s.money).toBeGreaterThanOrEqual(0);
        expect(s.debt).toBeGreaterThanOrEqual(0);
        Object.values(s.stats).forEach((n) => {
          expect(n).toBeGreaterThanOrEqual(0);
          expect(n).toBeLessThanOrEqual(100);
        });
      }
      expect(s.dead, `seed ${seed} must finish`).toBe(true);
      expect(ENDINGS.some((e) => e.id === s.ending)).toBe(true);
    }
  });
});

describe("finance input safety", () => {
  it("refuses invalid repayment amounts and a second outstanding loan", () => {
    const s = adult();
    s.debt = 50_000;
    for (const amount of [-100, 0, NaN, Infinity])
      expect(act(s, { type: "repay", amount })).toEqual(s);
    expect(act(s, { type: "loan", amount: 50_000 })).toEqual(s);
  });
  it("applies annual interest when a penniless unemployed adult cannot pay", () => {
    const s = adult();
    s.money = 0;
    s.debt = 100_000;
    const next = act(s, { type: "study" });
    expect(next.debt).toBeCloseTo(112_000);
    expect(next.money).toBe(0);
    expect(next.stats.stress).toBeGreaterThan(s.stats.stress);
  });
});

describe("achievement reachability", () => {
  it("provides a triggering state for every shipped achievement", () => {
    const all = new Set<string>();
    const collect = (s: GameState) => earned(s).forEach((id) => all.add(id));
    const strong = adult();
    strong.age = 90;
    strong.turn = 90;
    strong.money = 1e9;
    strong.debt = 1000;
    strong.careerLevel = 3;
    strong.stats = {
      health: 100,
      intellect: 100,
      charisma: 100,
      luck: 100,
      stress: 0,
      reputation: 100,
    };
    strong.properties = PROPERTIES.map((p) => p.id);
    strong.flags = { repaid: 1, study: 10, rest: 15, work: 20, chainStage: 1 };
    strong.seen = Array.from({ length: 60 }, (_, i) => String(i));
    strong.relationships = Array.from({ length: 5 }, (_, i) => ({
      name: String(i),
      bond: 95,
      role: i === 0 ? "супруг" : "партнёр",
      memory: [],
    }));
    strong.dead = true;
    strong.ending = endingFor(strong);
    collect(strong);
    for (const job of JOBS) collect({ ...strong, job: job.id });
    const weak = adult();
    weak.age = 20;
    weak.money = 0;
    weak.dead = true;
    weak.stats = {
      health: 0,
      intellect: 0,
      charisma: 0,
      luck: 0,
      stress: 100,
      reputation: 0,
    };
    collect(weak);
    expect([...all].sort()).toEqual(ACHIEVEMENTS.map((a) => a.id).sort());
  });
});

describe("authored event integrity", () => {
  it("ships at least 150 unique complete events with meaningful choices", async () => {
    const { EVENTS } = await import("./events");
    expect(EVENTS.length).toBeGreaterThanOrEqual(150);
    expect(new Set(EVENTS.map((e) => e.id)).size).toBe(EVENTS.length);
    expect(new Set(EVENTS.map((e) => e.title)).size).toBe(EVENTS.length);
    expect(new Set(EVENTS.map((e) => e.description)).size).toBe(EVENTS.length);
    for (const e of EVENTS) {
      expect(e.choices.length).toBeGreaterThanOrEqual(3);
      expect(e.choices.length).toBeLessThanOrEqual(5);
      expect(e.description.length).toBeGreaterThan(15);
      for (const c of e.choices) {
        expect(c.text.length).toBeGreaterThan(2);
        expect(c.result.length).toBeGreaterThan(10);
        for (const [key, value] of Object.entries(c.effects ?? {})) {
          expect([
            "health",
            "intellect",
            "charisma",
            "luck",
            "stress",
            "reputation",
            "money",
            "debt",
          ]).toContain(key);
          expect(Number.isFinite(value)).toBe(true);
        }
      }
    }
  });
});

describe("butterfly story chains", () => {
  it("completes ten three-stage stories with three distinct final choices each", async () => {
    const { EVENTS } = await import("./events");
    const names = [
      ...new Set(
        EVENTS.filter((e) => e.id.startsWith("chain-")).map(
          (e) => e.id.split("-")[1],
        ),
      ),
    ];
    expect(names.length).toBeGreaterThanOrEqual(10);
    for (const name of names)
      for (const final of [0, 1, 2]) {
        let s = adult(101);
        s.money = 10_000_000;
        s.stats.health = 100;
        s.stats.stress = 0;
        for (const stage of [1, 2, 3]) {
          const e = EVENTS.find((e) => e.id === `chain-${name}-${stage}`)!;
          expect(e).toBeDefined();
          s.age = Math.max(s.age, e.minAge ?? 0);
          s.turn = s.age;
          s.currentEvent = e.id;
          for (const [flag, value] of Object.entries(e.requires ?? {}))
            expect(s.flags[flag]).toBeGreaterThanOrEqual(value);
          s = choose(s, stage === 3 ? final : final % 2);
          expect(s.dead).toBe(false);
          expect(validateSave(s)).toBe(true);
        }
        expect(s.flags[`chain_${name}_complete`]).toBe(1);
        expect(s.flags[`ending_${name}_${final}`]).toBe(1);
        expect(s.flags.chainStage).toBe(1);
        expect(s.history).toHaveLength(3);
      }
  });
  it("remembers abandoning a story and does not unlock its next stage", async () => {
    const { EVENTS } = await import("./events");
    for (const e of EVENTS.filter((e) => /^chain-.*-1$/.test(e.id))) {
      let s = adult();
      s.age = Math.max(s.age, e.minAge ?? 0);
      s.turn = s.age;
      s.currentEvent = e.id;
      s = choose(s, 2);
      const name = e.id.split("-")[1];
      expect(s.flags[`chain_${name}_abandoned`]).toBe(1);
      expect(s.flags[`chain_${name}_1`]).toBeUndefined();
      const next = EVENTS.find((x) => x.id === `chain-${name}-2`)!;
      expect(
        Object.entries(next.requires ?? {}).every(
          ([flag, value]) => (s.flags[flag] ?? 0) >= value,
        ),
      ).toBe(false);
    }
  });
});

describe("story chronology", () => {
  it("never schedules a later chapter before the prerequisite decision", async () => {
    const { EVENTS } = await import("./events");
    for (const e of EVENTS.filter(
      (e) => e.id.startsWith("chain-") && e.requires,
    )) {
      const s = adult();
      s.age = Math.max(s.age, e.minAge ?? 0);
      s.turn = s.age;
      s.currentEvent = "";
      s.seen = EVENTS.filter((x) => x.id !== e.id).map((x) => x.id);
      expect(selectEvent(s).id).toBe("ordinary");
      Object.assign(s.flags, e.requires);
      expect(selectEvent(s).id).toBe(e.id);
    }
  });
});
