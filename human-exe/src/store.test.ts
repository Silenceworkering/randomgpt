import "fake-indexeddb/auto";
import { describe, it, expect } from "vitest";
import { useGameStore } from "./store";
import { loadGame } from "./persistence";
describe("ordered autosave", () => {
  it("keeps the latest rapid decision after reloading and clears on reset", async () => {
    const store = useGameStore.getState();
    await store.reset();
    store.newGame();
    for (let i = 0; i < 12; i++) useGameStore.getState().act({ type: "study" });
    const latest = structuredClone(useGameStore.getState().game);
    await useGameStore.getState().save();
    expect(await loadGame()).toEqual(latest);
    useGameStore.setState({ game: null });
    await useGameStore.getState().load();
    expect(useGameStore.getState().game).toEqual(latest);
    await useGameStore.getState().reset();
    expect(await loadGame()).toBeNull();
  });
  it("rejects invalid imports and preserves the current life", async () => {
    useGameStore.getState().newGame();
    await useGameStore.getState().save();
    const before = useGameStore.getState().game;
    await expect(useGameStore.getState().importGame("{}")).rejects.toThrow();
    expect(useGameStore.getState().game).toEqual(before);
    expect(await loadGame()).toEqual(before);
  });
});
