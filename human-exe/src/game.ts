import type { GameState, Action, Stats, GameEvent } from "./types";
import { EVENTS } from "./events";
import {
  JOBS,
  PROPERTIES,
  earned,
  endingFor,
  ACHIEVEMENTS,
  ENDINGS,
} from "./catalogs";
export { JOBS, PROPERTIES, ACHIEVEMENTS, ENDINGS } from "./catalogs";
const clamp = (v: number, min = 0, max = 100) =>
  Math.max(min, Math.min(max, v));
function random(s: GameState) {
  s.rng = (Math.imul(s.rng, 1664525) + 1013904223) >>> 0;
  return s.rng / 4294967296;
}
const traits = [
  "Боится налоговой",
  "Гений бесполезных решений",
  "Любимчик бабушки",
  "Аллергия на работу",
  "Финансовый гений наоборот",
  "Потомственный неудачник",
];
export function createGame(seed = Date.now() >>> 0): GameState {
  seed = seed >>> 0;
  const s: GameState = {
    version: 1,
    seed,
    rng: seed >>> 0,
    age: 0,
    turn: 0,
    name: "",
    surname: "",
    city: "",
    money: 0,
    stats: {
      health: 85,
      intellect: 35,
      charisma: 40,
      luck: 40,
      stress: 5,
      reputation: 40,
    },
    traits: [],
    job: null,
    careerLevel: 1,
    debt: 0,
    properties: [],
    relationships: [{ name: "Бабушка", bond: 65, role: "семья", memory: [] }],
    flags: {},
    seen: [],
    history: [],
    achievements: [],
    currentEvent: "",
    dead: false,
    ending: null,
    lastResult: "Вы родились. Служба поддержки отказалась принимать возврат.",
  };
  const pick = (a: string[]) => a[Math.floor(random(s) * a.length)];
  s.name = pick([
    "Саша",
    "Женя",
    "Валера",
    "Никита",
    "Даша",
    "Алексей",
    "Аня",
    "Миша",
  ]);
  s.surname = pick([
    "Пельменев",
    "Суетин",
    "Бубликов",
    "Неудачин",
    "Козырев",
    "Петров",
    "Сковородин",
  ]);
  s.city = pick([
    "Омск",
    "Пермь",
    "Воронеж",
    "Тула",
    "Казань",
    "Челябинск",
    "Саратов",
    "Новосибирск",
    "Владивосток",
    "Тверь",
  ]);
  s.money = Math.floor(random(s) * 30000);
  s.traits = [pick(traits)];
  for (const k of ["intellect", "charisma", "luck"] as const)
    s.stats[k] = 20 + Math.floor(random(s) * 45);
  s.currentEvent = selectEvent(s).id;
  return s;
}
const fallback: GameEvent = {
  id: "ordinary",
  title: "Обычный год. Подозрительно.",
  description: "Новости закончились, жизнь почему-то продолжается.",
  category: "Абсурд",
  choices: [
    {
      text: "Отдохнуть",
      result: "Вы ничего не добились. Зато с нормальным пульсом.",
      effects: { health: 8, stress: -12 },
    },
    {
      text: "Учиться",
      result: "Вы узнали больше. Это не сделало мир понятнее.",
      effects: { intellect: 5, stress: 3 },
    },
    {
      text: "Позвонить близким",
      result: "Теперь кто-то знает, что вы живы.",
      effects: { charisma: 3, stress: -5 },
      relationship: 6,
    },
  ],
};
function eligible(s: GameState, e: GameEvent): boolean {
  return (
    !s.seen.includes(e.id) &&
    s.age >= (e.minAge ?? 0) &&
    s.age <= (e.maxAge ?? 100) &&
    (!e.job || s.job === e.job) &&
    (!e.property || s.properties.includes(e.property)) &&
    s.money >= (e.minMoney ?? 0) &&
    s.stats.reputation >= (e.minReputation ?? 0) &&
    s.relationships.some(
      (r) =>
        (!e.romantic || r.role === "партнёр" || r.role === "супруг") &&
        r.bond >= (e.minBond ?? 0),
    ) &&
    Object.entries(e.requires ?? {}).every(([k, v]) => (s.flags[k] ?? 0) >= v)
  );
}
export function selectEvent(s: GameState): GameEvent {
  if (s.currentEvent) {
    const existing = EVENTS.find((e) => e.id === s.currentEvent);
    if (existing) return existing;
  }
  const available = EVENTS.filter((e) => eligible(s, e));
  const chains = available.filter((e) => Object.keys(e.requires ?? {}).length);
  const list = chains.length ? chains : available;
  return list.length
    ? list[Math.floor((((s.rng >>> 0) % 100000) / 100000) * list.length)]
    : fallback;
}
function effects(
  s: GameState,
  e: Partial<Stats> & { money?: number; debt?: number },
) {
  for (const k of Object.keys(s.stats) as (keyof Stats)[])
    s.stats[k] = clamp(s.stats[k] + (e[k] ?? 0));
  s.money = clamp(s.money + (e.money ?? 0), 0, 1e12);
  s.debt = clamp(s.debt + (e.debt ?? 0), 0, 1e12);
}
function tick(s: GameState, title: string, text: string) {
  random(s);
  s.age++;
  s.turn++;
  let income = 0,
    cost = 0;
  const job = JOBS.find((j) => j.id === s.job);
  if (s.age >= 18) {
    income = (job?.salary ?? 0) * 12 * s.careerLevel;
    cost =
      120000 + (s.relationships.some((r) => r.role === "супруг") ? 60000 : 0);
    for (const id of s.properties) {
      const p = PROPERTIES.find((p) => p.id === id);
      if (p) {
        income += p.income * 12;
        cost += p.maintenance * 12;
        if (p.income > 40000 && random(s) < 0.15) {
          income -= p.income * 9;
          s.stats.stress += 8;
          text += " Бизнес пережил внеплановую проверку и плановую панику.";
        }
      }
    }
    if (s.properties.includes("flat") || s.properties.includes("house"))
      cost -= 60000;
    if (s.debt) {
      s.debt *= 1.12;
      const payment = Math.min(s.money + income, s.debt * 0.08);
      s.debt -= payment;
      cost += payment;
    }
    if (s.money + income < cost) {
      s.stats.stress += 8;
      s.stats.health -= 3;
    }
    s.money = clamp(s.money + income - cost, 0, 1e12);
  }
  if (s.traits.includes("Любимчик бабушки") && s.age < 25) s.money += 5000;
  if (s.traits.includes("Аллергия на работу") && job) s.stats.stress += 3;
  if (s.traits.includes("Финансовый гений наоборот") && income > 0)
    s.money *= 0.98;
  if (s.traits.includes("Боится налоговой") && s.money > 1e6)
    s.stats.stress += 2;
  if (s.traits.includes("Потомственный неудачник") && random(s) < 0.08) {
    s.money = Math.max(0, s.money - 15000);
    text += " Семейная неудача передаёт привет.";
  }
  if (s.traits.includes("Гений бесполезных решений")) s.stats.intellect += 0.5;
  if (s.age > 50) s.stats.health -= 1 + (s.age - 50) * 0.07;
  if (s.stats.stress > 75) s.stats.health -= 3;
  for (const k of Object.keys(s.stats) as (keyof Stats)[])
    s.stats[k] = clamp(s.stats[k]);
  if (s.age >= 18 && random(s) < (100 - s.stats.luck) / 1500) {
    s.money = Math.max(0, s.money - 10000);
    text += " Удача ушла покурить: внезапный счёт на 10 000 ₽.";
  }
  s.history.push({ age: s.age, title, text });
  s.lastResult = text;
  s.currentEvent = "";
  if (s.stats.health <= 0 || s.age >= 90) {
    s.dead = true;
    s.ending = endingFor(s);
    s.lastResult += ` HUMAN.EXE завершил работу. ${s.seen.length} событий; капитал ${Math.round(s.money).toLocaleString("ru-RU")} ₽; долг ${Math.round(s.debt).toLocaleString("ru-RU")} ₽. Последняя профессия: ${JOBS.find((j) => j.id === s.job)?.name ?? "свободный человек"}.`;
  } else s.currentEvent = selectEvent(s).id;
  s.achievements = [...new Set([...s.achievements, ...earned(s)])];
  return s;
}
export function choose(state: GameState, index: number): GameState {
  if (state.dead) return state;
  const e = selectEvent(state),
    c = e.choices[index];
  if (!c || (e.romantic && !eligible(state, e))) return state;
  const s = structuredClone(state);
  effects(s, c.effects ?? {});
  for (const [k, v] of Object.entries(c.flags ?? {}))
    s.flags[k] = (s.flags[k] ?? 0) + v;
  if (e.requires && Object.keys(e.requires).length) s.flags.chainStage = 1;
  if (c.job && JOBS.some((j) => j.id === c.job) && s.age >= 17) s.job = c.job;
  if (
    c.property &&
    PROPERTIES.some((p) => p.id === c.property) &&
    !s.properties.includes(c.property)
  )
    s.properties.push(c.property);
  if (c.relationship) {
    const r = (
      e.romantic
        ? [...s.relationships]
            .reverse()
            .find((r) => r.role === "партнёр" || r.role === "супруг")
        : s.relationships[s.relationships.length - 1]
    )!;
    r.bond = clamp(r.bond + c.relationship);
    r.memory.push(c.result);
    if (r.role === "супруг" && r.bond < 25) {
      r.role = "бывший супруг";
      s.stats.stress = clamp(s.stats.stress + 15);
      s.money *= 0.7;
      s.flags.divorced = 1;
    }
  }
  if (e.id !== "ordinary") s.seen.push(e.id);
  return tick(s, e.title, c.result);
}
export function act(state: GameState, a: Action): GameState {
  if (
    state.dead ||
    ![
      "work",
      "rest",
      "study",
      "social",
      "job",
      "buy",
      "loan",
      "repay",
      "intimacy",
    ].includes(a.type)
  )
    return state;
  const s = structuredClone(state);
  let text = "";
  if (a.type === "job") {
    const j = JOBS.find((x) => x.id === a.id);
    if (
      !j ||
      s.age < 18 ||
      s.stats.intellect < j.intellect ||
      s.stats.charisma < j.charisma
    )
      return state;
    s.job = j.id;
    s.careerLevel = 1;
    text = `Вы устроились: ${j.name}. Испытательный срок — жизнь.`;
  }
  if (a.type === "buy") {
    const p = PROPERTIES.find((x) => x.id === a.id);
    if (!p || s.age < 18 || s.money < p.price || s.properties.includes(p.id))
      return state;
    s.money -= p.price;
    s.properties.push(p.id);
    text = `Куплено: ${p.name}. Теперь у проблем есть адрес.`;
  }
  if (a.type === "loan") {
    if (a.amount !== undefined && (!Number.isFinite(a.amount) || a.amount <= 0))
      return state;
    const amount = clamp(a.amount ?? 150000, 10000, 1000000);
    if (
      s.age < 18 ||
      s.debt > 0 ||
      amount >
        Math.max(150000, (JOBS.find((j) => j.id === s.job)?.salary ?? 0) * 18)
    )
      return state;
    s.debt = amount;
    s.money += amount;
    text = "Банк поверил в ваше будущее. Очень дорого.";
  }
  if (a.type === "repay") {
    if (
      !s.debt ||
      !s.money ||
      (a.amount !== undefined && (!Number.isFinite(a.amount) || a.amount <= 0))
    )
      return state;
    const v = Math.min(s.money, s.debt, a.amount ?? s.debt);
    s.money -= v;
    s.debt -= v;
    if (s.debt < 1) {
      s.debt = 0;
      s.flags.repaid = 1;
    }
    text = "Часть будущего снова принадлежит вам.";
  }
  if (a.type === "study") {
    effects(s, { intellect: 7, stress: 3, money: s.age >= 18 ? -10000 : 0 });
    s.flags.study = (s.flags.study ?? 0) + 1;
    text = "Вы учились. Диплом пока не обещали.";
  }
  if (a.type === "rest") {
    effects(s, { health: 12, stress: -20 });
    s.flags.rest = (s.flags.rest ?? 0) + 1;
    text = "Год отдыха. Производительность дивана выросла.";
  }
  if (a.type === "work") {
    if (!s.job || s.age < 18) return state;
    const j = JOBS.find((j) => j.id === s.job)!;
    s.flags.work = (s.flags.work ?? 0) + 1;
    effects(s, { stress: 10, health: -2, intellect: 1, money: j.salary * 2 });
    if (s.flags.work % 3 === 0)
      s.careerLevel = clamp(s.careerLevel + 0.25, 1, 3);
    if (random(s) * 100 < j.risk) {
      effects(s, { health: -10, money: -j.salary });
      text = "Рабочий риск сработал. Премию заменили сочувствием.";
    } else
      text = "Вы работали сверхурочно. Время вернуть нельзя, деньги можно.";
  }
  if (a.type === "intimacy") {
    const partner = [...s.relationships]
      .reverse()
      .find(
        (r) => (r.role === "партнёр" || r.role === "супруг") && r.bond >= 65,
      );
    if (s.age < 18 || !partner) return state;
    effects(s, { stress: -10, health: 1, charisma: 1 });
    partner.bond = clamp(partner.bond + 5);
    partner.memory.push(
      "Вы обсудили желания и границы. Близость была по взаимному согласию.",
    );
    s.flags.intimacy = (s.flags.intimacy ?? 0) + 1;
    text =
      "Год близости с " +
      partner.name +
      ". Оба согласились, позаботились о защите и уважали границы. Семейному чату ничего не сообщили.";
  }
  if (a.type === "social") {
    s.flags.social = (s.flags.social ?? 0) + 1;
    effects(s, { charisma: 5, stress: -8, money: s.age >= 18 ? -8000 : 0 });
    if (s.age >= 18 && s.relationships.length < 8 && random(s) < 0.35)
      s.relationships.push({
        name: ["Лера", "Семён", "Ира", "Макс", "Оля", "Илья", "Катя"][
          s.relationships.length - 1
        ],
        bond: 35,
        role: "друг",
        memory: ["Познакомились на встрече"],
      });
    const r = s.relationships[s.relationships.length - 1];
    r.bond = clamp(r.bond + 12);
    if (s.age >= 18 && r.role === "друг" && r.bond >= 65) r.role = "партнёр";
    else if (r.role === "партнёр" && r.bond >= 90) {
      r.role = "супруг";
      s.flags.married = 1;
    }
    s.relationships.forEach((r) =>
      r.memory.push("Вы нашли время для встречи."),
    );
    text = "Встретились с близкими. Семейный чат временно обезврежен.";
  }
  return tick(s, "Личное решение", text);
}
function validateSaveUnsafe(value: unknown): value is GameState {
  if (!value || typeof value !== "object") return false;
  const s = value as GameState;
  const num = (v: unknown) => typeof v === "number" && Number.isFinite(v);
  if (
    s.version !== 1 ||
    !Number.isInteger(s.seed) ||
    s.seed < 0 ||
    s.seed > 4294967295 ||
    !Number.isInteger(s.rng) ||
    s.rng < 0 ||
    s.rng > 4294967295 ||
    !Number.isInteger(s.turn) ||
    s.turn < 0 ||
    s.turn > 100 ||
    !num(s.age) ||
    s.age < 0 ||
    s.age > 90 ||
    s.age !== s.turn ||
    !num(s.money) ||
    s.money < 0 ||
    s.money > 1e12 ||
    !num(s.debt) ||
    s.debt < 0 ||
    s.debt > 1e12 ||
    !num(s.careerLevel) ||
    s.careerLevel < 1 ||
    s.careerLevel > 3
  )
    return false;
  if (
    !s.stats ||
    Array.isArray(s.stats) ||
    typeof s.stats !== "object" ||
    !["health", "intellect", "charisma", "luck", "stress", "reputation"].every(
      (k) =>
        num(s.stats[k as keyof Stats]) &&
        s.stats[k as keyof Stats] >= 0 &&
        s.stats[k as keyof Stats] <= 100,
    )
  )
    return false;
  if (
    !["name", "surname", "city", "currentEvent", "lastResult"].every(
      (k) =>
        typeof s[k as keyof GameState] === "string" &&
        (s[k as keyof GameState] as string).length < 20000,
    )
  )
    return false;
  if (
    !Array.isArray(s.traits) ||
    s.traits.length > 6 ||
    !s.traits.every((x) => traits.includes(x)) ||
    !s.traits.every((x) => typeof x === "string") ||
    !Array.isArray(s.properties) ||
    new Set(s.properties).size !== s.properties.length ||
    !s.properties.every((id) => PROPERTIES.some((p) => p.id === id)) ||
    !Array.isArray(s.seen) ||
    s.seen.length > 1000 ||
    new Set(s.seen).size !== s.seen.length ||
    !s.seen.every((id) => EVENTS.some((e) => e.id === id)) ||
    !Array.isArray(s.achievements) ||
    s.achievements.length > 50 ||
    new Set(s.achievements).size !== s.achievements.length ||
    !s.achievements.every((x) => ACHIEVEMENTS.some((a) => a.id === x))
  )
    return false;
  if (s.job !== null && !JOBS.some((j) => j.id === s.job)) return false;
  if (
    typeof s.dead !== "boolean" ||
    (s.ending !== null && !ENDINGS.some((e) => e.id === s.ending)) ||
    s.dead !== (s.ending !== null) ||
    (s.dead && s.age < 90 && s.stats.health > 0) ||
    (!s.dead && (s.age >= 90 || s.stats.health <= 0)) ||
    (!s.dead &&
      s.currentEvent !== "ordinary" &&
      !EVENTS.some((e) => e.id === s.currentEvent)) ||
    !s.flags ||
    typeof s.flags !== "object" ||
    Array.isArray(s.flags) ||
    Object.keys(s.flags).some((k) =>
      ["__proto__", "constructor", "prototype"].includes(k),
    ) ||
    Object.keys(s.flags).length > 1000 ||
    Object.values(s.flags).some((x) => !num(x))
  )
    return false;
  if (
    !Array.isArray(s.history) ||
    s.history.length > 200 ||
    !s.history.every(
      (h) =>
        h &&
        typeof h === "object" &&
        num(h.age) &&
        h.age >= 0 &&
        h.age <= s.age &&
        typeof h.title === "string" &&
        h.title.length < 1000 &&
        typeof h.text === "string" &&
        h.text.length < 20000,
    )
  )
    return false;
  if (
    !Array.isArray(s.relationships) ||
    !s.relationships.length ||
    s.relationships.length > 20 ||
    !s.relationships.every(
      (r) =>
        r &&
        typeof r === "object" &&
        typeof r.name === "string" &&
        r.name.length < 200 &&
        typeof r.role === "string" &&
        ["семья", "друг", "партнёр", "супруг", "бывший супруг"].includes(
          r.role,
        ) &&
        num(r.bond) &&
        r.bond >= 0 &&
        r.bond <= 100 &&
        Array.isArray(r.memory) &&
        r.memory.length < 201 &&
        r.memory.every((x) => typeof x === "string" && x.length < 20000),
    )
  )
    return false;
  if (!s.dead) {
    const current = EVENTS.find((e) => e.id === s.currentEvent);
    if (
      current
        ? !eligible(s, current)
        : s.currentEvent !== "ordinary" || EVENTS.some((e) => eligible(s, e))
    )
      return false;
  }
  return true;
}

export function validateSave(value: unknown): value is GameState {
  try {
    return validateSaveUnsafe(value);
  } catch {
    return false;
  }
}
