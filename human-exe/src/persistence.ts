import type { GameState } from "./types";
import { validateSave } from "./game";
const DB = "human-exe-v1";
function open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB, 1);
    request.onupgradeneeded = () => request.result.createObjectStore("saves");
    request.onsuccess = () => resolve(request.result);
    request.onerror = () =>
      reject(new Error("Хранилище недоступно. Экспортируйте жизнь в JSON."));
  });
}
async function transaction<T>(
  mode: IDBTransactionMode,
  operation: (store: IDBObjectStore) => IDBRequest,
): Promise<T> {
  const db = await open();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("saves", mode);
    const request = operation(tx.objectStore("saves"));
    let result: T;
    request.onsuccess = () => {
      result = request.result as T;
    };
    tx.oncomplete = () => {
      db.close();
      resolve(result);
    };
    tx.onerror = () => {
      db.close();
      reject(tx.error ?? new Error("Ошибка сохранения"));
    };
    tx.onabort = () => {
      db.close();
      reject(tx.error ?? new Error("Сохранение отменено"));
    };
  });
}
export function parseImport(text: string): GameState {
  if (text.length > 2_000_000)
    throw new Error("Слишком большой файл (максимум 2 МБ).");
  let value: unknown;
  try {
    value = JSON.parse(text);
  } catch {
    throw new Error("Файл не является JSON.");
  }
  if (!validateSave(value))
    throw new Error("Сохранение повреждено или несовместимо.");
  return value as GameState;
}
export async function saveGame(game: GameState): Promise<void> {
  if (!validateSave(game)) throw new Error("Некорректное состояние игры.");
  await transaction("readwrite", (store) =>
    store.put(structuredClone(game), "autosave"),
  );
}
export async function loadGame(): Promise<GameState | null> {
  const value = await transaction<unknown>("readonly", (store) =>
    store.get("autosave"),
  );
  if (value === undefined) return null;
  if (!validateSave(value))
    throw new Error("Автосохранение повреждено. Импортируйте резервную копию.");
  return value as GameState;
}
export async function clearSave(): Promise<void> {
  await transaction("readwrite", (store) => store.delete("autosave"));
}
