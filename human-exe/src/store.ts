import { create } from "zustand";
import { createGame, choose, act } from "./game";
import type { Action, GameState } from "./types";
import { saveGame, loadGame, clearSave, parseImport } from "./persistence";
type Settings = { sound: boolean; animations: boolean };
interface Store {
  game: GameState | null;
  ready: boolean;
  error: string;
  settings: Settings;
  init: () => Promise<void>;
  newGame: () => void;
  choose: (index: number) => void;
  act: (action: Action) => void;
  save: () => Promise<void>;
  load: () => Promise<void>;
  importGame: (text: string) => Promise<void>;
  reset: () => Promise<void>;
  setSettings: (settings: Partial<Settings>) => void;
}
let queue = Promise.resolve();
function persist(game: GameState) {
  queue = queue.catch(() => {}).then(() => saveGame(game));
  queue.catch((error) =>
    useGameStore.setState({ error: String(error.message ?? error) }),
  );
  return queue;
}
function initialSettings(): Settings {
  try {
    const raw = JSON.parse(localStorage.getItem("human-exe-settings") ?? "{}");
    return {
      sound: raw?.sound === true,
      animations: raw?.animations !== false,
    };
  } catch {
    return { sound: false, animations: true };
  }
}
export const useGameStore = create<Store>((set, get) => ({
  game: null,
  ready: false,
  error: "",
  settings: initialSettings(),
  init: async () => {
    try {
      const game = await loadGame();
      set({ game, ready: true });
    } catch (error) {
      set({ ready: true, error: String((error as Error).message) });
    }
  },
  newGame: () => {
    const game = createGame();
    set({ game, error: "" });
    void persist(game);
  },
  choose: (index) => {
    const old = get().game;
    if (!old) return;
    const game = choose(old, index);
    set({ game, error: "" });
    void persist(game);
  },
  act: (action) => {
    const old = get().game;
    if (!old) return;
    const game = act(old, action);
    set({ game, error: "" });
    void persist(game);
  },
  save: async () => {
    const game = get().game;
    if (game) {
      await persist(game);
      set({ error: "" });
    }
  },
  load: async () => {
    await queue.catch(() => {});
    const game = await loadGame();
    set({ game, error: "" });
  },
  importGame: async (text) => {
    const game = parseImport(text);
    await persist(game);
    set({ game, error: "" });
  },
  reset: async () => {
    await queue.catch(() => {});
    await clearSave();
    set({ game: null, error: "" });
  },
  setSettings: (settings) => {
    const merged = { ...get().settings, ...settings };
    set({ settings: merged });
    try {
      localStorage.setItem("human-exe-settings", JSON.stringify(merged));
    } catch {
      set({ error: "Настройки не сохранились: браузер запретил хранилище." });
    }
  },
}));
