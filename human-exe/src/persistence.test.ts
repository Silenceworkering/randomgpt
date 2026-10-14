import "fake-indexeddb/auto";
import { beforeEach, describe, expect, it } from "vitest";
import { createGame } from "./game";
import { clearSave, loadGame, parseImport, saveGame } from "./persistence";

beforeEach(async () => {
  await clearSave();
});
describe("IndexedDB saves", () => {
  it("starts empty and persists an independent full copy", async () => {
    expect(await loadGame()).toBeNull();
    const game = createGame(17);
    const snapshot = structuredClone(game);
    await saveGame(game);
    game.money += 1000;
    expect(await loadGame()).toEqual(snapshot);
    await clearSave();
    expect(await loadGame()).toBeNull();
  });
  it("replaces autosave atomically with the newest life", async () => {
    await saveGame(createGame(12));
    const second = createGame(99);
    await saveGame(second);
    expect(await loadGame()).toEqual(second);
  });
  it("round-trips exported JSON", () => {
    const game = createGame(123);
    expect(parseImport(JSON.stringify(game))).toEqual(game);
  });
  it.each(["{", "null", "{}", "[]", '{"version":9000}', "x".repeat(2_000_001)])(
    "rejects malformed or incompatible imports",
    (text) => {
      expect(() => parseImport(text)).toThrow();
    },
  );
  it("rejects corrupted nested state without replacing the previous save", async () => {
    const valid = createGame(1);
    await saveGame(valid);
    const corrupted = { ...valid, stats: { ...valid.stats, health: -12 } };
    expect(() => parseImport(JSON.stringify(corrupted))).toThrow();
    await expect(saveGame(corrupted)).rejects.toThrow();
    expect(await loadGame()).toEqual(valid);
  });
});

describe("malformed nested imports", () => {
  it.each([
    { history: [null] },
    { relationships: [null] },
    { relationships: [{}] },
    { history: [{}] },
    { seen: ["event-that-does-not-exist"] },
    { flags: { nested: { value: 1 } } },
    { flags: null },
    { stats: null },
    { achievements: [null] },
    { properties: [null] },
    {
      relationships: [{ name: "Ошибка", role: "друг", bond: 50, memory: null }],
    },
  ])("rejects nested corruption with a useful import error", (patch) => {
    const data = JSON.stringify({ ...createGame(71), ...patch });
    expect(() => parseImport(data)).toThrow(
      "Сохранение повреждено или несовместимо.",
    );
  });
});
