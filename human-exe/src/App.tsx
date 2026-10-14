import { useEffect, useRef, useState } from "react";
import { useGameStore } from "./store";
import { selectEvent, JOBS, PROPERTIES, ACHIEVEMENTS, ENDINGS } from "./game";
import type { Action, Stats } from "./types";
import "./styles.css";
import { newsFor, rumorFor } from "./news";
const years = (n: number) =>
  `${n} ${n % 100 >= 11 && n % 100 <= 14 ? "лет" : n % 10 === 1 ? "год" : n % 10 >= 2 && n % 10 <= 4 ? "года" : "лет"}`;
const cash = (v: number) =>
  new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 }).format(v) + " ₽";
const labels: Record<keyof Stats, string> = {
  health: "♥ Здоровье",
  intellect: "◈ Интеллект",
  charisma: "✦ Харизма",
  luck: "♣ Удача",
  stress: "ϟ Стресс",
  reputation: "◎ Репутация",
};
const tabs = [
  ["life", "Жизнь"],
  ["career", "Карьера"],
  ["assets", "Имущество"],
  ["people", "Связи"],
  ["history", "История"],
  ["stats", "Статистика"],
  ["achievements", "Достижения"],
  ["settings", "Настройки"],
];
function Portrait() {
  return (
    <svg
      viewBox="0 0 200 160"
      className="portrait"
      aria-label="Пиксельный портрет персонажа"
    >
      <defs>
        <pattern id="grid" width="16" height="16" patternUnits="userSpaceOnUse">
          <path d="M16 0H0V16" fill="none" stroke="#273529" strokeWidth=".6" />
        </pattern>
      </defs>
      <rect width="200" height="160" fill="url(#grid)" />
      <path d="M67 25h66v15h15v69h-15v18H67v-18H52V40h15z" fill="#bad1a4" />
      <path
        d="M67 25h66v16H67zM52 40h15v35H52zM133 40h15v37h-15z"
        fill="#2b3a2b"
      />
      <path d="M77 68h14v14H77zM111 68h14v14h-14z" fill="#131912" />
      <path d="M90 101h24v5H90z" fill="#47573c" />
      <path d="M68 128h65l25 32H42z" fill="#99ff4e" />
      <path d="M92 128h19v32H92z" fill="#355124" />
      <path
        d="M13 13h22M13 13v22M187 13h-22M187 13v22M13 147h22M13 147v-22M187 147h-22M187 147v-22"
        stroke="#9dff4e"
        fill="none"
      />
    </svg>
  );
}
function eventSymbol(category: string) {
  return /Криминал/.test(category)
    ? "⌁"
    : /Бизнес|Финанс|Работа/.test(category)
      ? "↗"
      : /Здоровье/.test(category)
        ? "♥"
        : /Образование/.test(category)
          ? "◈"
          : /Недвижимость/.test(category)
            ? "⌂"
            : /Отношения|Семья|Друзья/.test(category)
              ? "◎"
              : /Политика/.test(category)
                ? "⚑"
                : /Путешествия/.test(category)
                  ? "⌖"
                  : "✦";
}
function EventArtwork({ category }: { category: string }) {
  const finance = /Бизнес|Финанс|Работа/.test(category),
    home = /Недвижимость/.test(category),
    crime = /Криминал|Политика/.test(category),
    mind = /Образование|Здоровье/.test(category);
  return (
    <svg className="event-artwork" viewBox="0 0 300 280" aria-hidden="true">
      <defs>
        <pattern
          id="eventdots"
          width="14"
          height="14"
          patternUnits="userSpaceOnUse"
        >
          <circle cx="1" cy="1" r=".8" fill="currentColor" opacity=".35" />
        </pattern>
        <linearGradient id="artfade" x2="0" y2="1">
          <stop stopColor="currentColor" stopOpacity=".19" />
          <stop offset="1" stopColor="currentColor" stopOpacity="0" />
        </linearGradient>
      </defs>
      <rect x="8" y="8" width="284" height="264" fill="url(#eventdots)" />
      <g fill="none" stroke="currentColor" strokeWidth="1">
        <circle cx="153" cy="140" r="108" opacity=".13" />
        <circle cx="153" cy="140" r="83" strokeDasharray="2 8" opacity=".4" />
        <path d="M12 140h44m194 0h38M153 7v40m0 186v40" opacity=".45" />
      </g>
      {finance ? (
        <g fill="none" stroke="currentColor">
          <path d="M62 210h189M65 204V78" opacity=".5" />
          <path d="M77 177l38-35 28 14 43-56 37-20" strokeWidth="3" />
          <path d="M205 80h20v20" strokeWidth="3" />
          <path
            d="M77 177l38-35 28 14 43-56 37-20v131H77z"
            fill="url(#artfade)"
            stroke="none"
          />
          {[100, 141, 182, 223].map((x, i) => (
            <path
              key={x}
              d={`M${x} 208v-${[23, 51, 70, 101][i]}`}
              opacity=".4"
              strokeWidth="12"
            />
          ))}
        </g>
      ) : home ? (
        <g stroke="currentColor" fill="none">
          <path d="M76 211V113h59V69h79v142M54 211h191" strokeWidth="2" />
          <path
            d="M87 131h12v14H87zm27 0h12v14h-12zm-27 32h12v14H87zm27 0h12v14h-12zM152 92h17v17h-17zm30 0h17v17h-17zm-30 36h17v17h-17zm30 0h17v17h-17z"
            opacity=".65"
          />
          <path d="M161 211v-35h28v35" />
        </g>
      ) : crime ? (
        <g stroke="currentColor" fill="none">
          <path
            d="M78 81h47l12 15h90v108H78z"
            fill="url(#artfade)"
            strokeWidth="2"
          />
          <path d="M94 120h117M94 140h72M94 157h94M94 174h59" opacity=".5" />
          <circle cx="210" cy="182" r="34" fill="#151c12" strokeWidth="2" />
          <path d="M210 165v21m0 8v4" strokeWidth="3" />
          <path d="M94 70h24M227 217h-24" opacity=".5" />
        </g>
      ) : mind ? (
        <g stroke="currentColor" fill="none">
          <path
            d="M149 78c-17-26-55-8-48 16-29 0-41 39-20 58-10 24 10 49 34 44 3 26 30 23 34 7V78zm4 0c17-26 55-8 48 16 29 0 41 39 20 58 10 24-10 49-34 44-3 26-30 23-34 7V78z"
            strokeWidth="2"
            fill="url(#artfade)"
          />
          <path
            d="M104 100l16 21-18 20 25 21-7 23M197 100l-16 21 18 20-25 21 7 23"
            opacity=".6"
          />
          <circle cx="126" cy="119" r="5" />
          <circle cx="177" cy="164" r="5" />
        </g>
      ) : (
        <g stroke="currentColor" fill="none">
          <ellipse
            cx="151"
            cy="140"
            rx="102"
            ry="42"
            transform="rotate(-32 151 140)"
            opacity=".6"
          />
          <ellipse
            cx="151"
            cy="140"
            rx="102"
            ry="42"
            transform="rotate(32 151 140)"
            opacity=".6"
          />
          <circle
            cx="151"
            cy="124"
            r="18"
            strokeWidth="2"
            fill="url(#artfade)"
          />
          <path d="M117 173c0-36 68-36 68 0" strokeWidth="2" />
          <circle cx="68" cy="178" r="6" fill="currentColor" />
          <circle cx="235" cy="102" r="5" fill="currentColor" />
          <circle cx="206" cy="192" r="4" fill="currentColor" />
        </g>
      )}
      <text
        x="148"
        y="255"
        textAnchor="middle"
        fill="currentColor"
        fontSize="8"
        letterSpacing="3"
        fontFamily="monospace"
      >
        HUMAN / LIFE SIGNAL
      </text>
    </svg>
  );
}
export default function App() {
  const s = useGameStore(),
    g = s.game;
  const [tab, setTab] = useState("life"),
    [accepted, setAccepted] = useState(false),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false),
    [toast, setToast] = useState("");
  const file = useRef<HTMLInputElement>(null),
    prev = useRef<string[] | null>(null);
  const lastGame = useRef<typeof g>(null);
  const [changes, setChanges] = useState<string[]>([]);
  useEffect(() => {
    void s.init();
  }, []);
  useEffect(() => {
    const old = lastGame.current;
    if (g && old && old.seed === g.seed && g.turn !== old.turn) {
      const deltas = Object.entries(g.stats)
        .filter(([k, v]) => v !== old.stats[k as keyof Stats])
        .map(
          ([k, v]) =>
            `${labels[k as keyof Stats]} ${v - old.stats[k as keyof Stats] > 0 ? "+" : ""}${v - old.stats[k as keyof Stats]}`,
        );
      if (g.money !== old.money)
        deltas.unshift(
          `Деньги ${g.money - old.money > 0 ? "+" : ""}${cash(g.money - old.money)}`,
        );
      setChanges(deltas);
    } else if (!g || !old || g.seed !== old.seed) setChanges([]);
    lastGame.current = g;
  }, [g]);
  useEffect(() => {
    if (!g) return;
    const fresh = g.achievements.filter((id) => !prev.current?.includes(id));
    if (prev.current && fresh.length)
      setToast(
        ACHIEVEMENTS.find((a) => a.id === fresh[0])?.name || "Новое достижение",
      );
    prev.current = g.achievements;
  }, [g?.achievements]);
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(""), 5000);
    return () => clearTimeout(t);
  }, [toast]);
  function beep() {
    if (!s.settings.sound) return;
    try {
      const c = new AudioContext(),
        o = c.createOscillator(),
        v = c.createGain();
      o.type = "triangle";
      o.frequency.value = 330;
      v.gain.setValueAtTime(0.035, c.currentTime);
      v.gain.exponentialRampToValueAtTime(0.001, c.currentTime + 0.13);
      o.connect(v);
      v.connect(c.destination);
      o.start();
      o.stop(c.currentTime + 0.14);
      o.onended = () => void c.close();
    } catch {}
  }
  async function run(fn: () => unknown, message?: string) {
    beep();
    setBusy(true);
    try {
      await fn();
      if (message) setNotice(message);
    } catch (e) {
      setNotice(
        e instanceof Error ? e.message : "Не удалось выполнить действие",
      );
    } finally {
      setBusy(false);
    }
  }
  const act = (a: Action) => void run(() => s.act(a));
  function exportGame() {
    if (!g) return;
    const url = URL.createObjectURL(
        new Blob([JSON.stringify(g, null, 2)], { type: "application/json" }),
      ),
      a = document.createElement("a");
    a.href = url;
    a.download = `human-exe-${g.age}.json`;
    a.click();
    URL.revokeObjectURL(url);
    setNotice("Резервная копия жизни готова.");
  }
  async function importGame(f?: File) {
    if (!f) return;
    if (f.size > 2000000) {
      setNotice("Максимальный размер файла — 2 МБ");
      return;
    }
    await run(async () => s.importGame(await f.text()), "Жизнь восстановлена");
    if (file.current) file.current.value = "";
  }
  const event = g && !g.dead ? selectEvent(g) : null,
    job = JOBS.find((j) => j.id === g?.job),
    ending = ENDINGS.find((e) => e.id === g?.ending);
  return (
    <div className={`app ${s.settings.animations ? "" : "no-motion"}`}>
      <header className="topbar">
        <a
          href="#"
          className="logo"
          onClick={(e) => {
            e.preventDefault();
            setTab("life");
          }}
        >
          HUMAN<span>.EXE</span>
          <i>●</i>
        </a>
        <div className="build">
          СИМУЛЯТОР ЖИЗНИ{" "}
          <span>
            v1.0 <b className="build-divider">/</b> LIFE SIMULATION{" "}
            <b className="build-divider">/</b> 18+
          </span>
        </div>
        <div className="status">
          <b>●</b>{" "}
          {g?.dead
            ? "ПРОЦЕСС ЗАВЕРШЁН"
            : g
              ? "ПРОЦЕСС ЗАПУЩЕН"
              : "ОЖИДАНИЕ РОЖДЕНИЯ"}
        </div>
      </header>
      {!s.ready ? (
        <main className="loading">Загружаем вашу сомнительную судьбу_</main>
      ) : !g ? (
        <main className="start">
          <div className="start-art">
            <Portrait />
            <code>
              &gt; human.spawn()
              <br />
              &gt; оптимизм не найден
              <br />
              &gt; запускаем как есть_
            </code>
          </div>
          <div className="eyebrow">НОВАЯ ЖИЗНЬ. НУЛЕВЫЕ ГАРАНТИИ.</div>
          <h1>
            Человек.
            <br />
            <em>Ошибка по умолчанию.</em>
          </h1>
          <p className="slogan">Ты родился. Уже хуёво. Дальше — хуже.</p>
          <p className="intro">
            От первого крика до последней квитанции. Работай, люби, рискуй и
            принимай решения, которые обязательно аукнутся. Хороших ответов нет.
            Твоя жизнь — есть.
          </p>
          <label className="consent">
            <input
              type="checkbox"
              checked={accepted}
              onChange={(e) => setAccepted(e.target.checked)}
            />{" "}
            Мне есть 18. Готов к мату, чёрному юмору и последствиям.
          </label>
          <button
            className="primary spawn"
            disabled={!accepted || busy}
            onClick={() => void run(() => s.newGame())}
          >
            РОДИТЬСЯ ↗
          </button>
          <button className="text-button" onClick={() => file.current?.click()}>
            ↥ Импортировать жизнь из JSON
          </button>
          <div className="start-footer">
            БЕЗ РЕГИСТРАЦИИ · БЕЗ СЕРВЕРОВ · С СОЖАЛЕНИЯМИ
          </div>
        </main>
      ) : (
        <main className="layout">
          <aside className="character panel">
            <div className="section-label">
              ОБЪЕКТ НАБЛЮДЕНИЯ <span>#{g.seed.toString(16).slice(0, 6)}</span>
            </div>
            <Portrait />
            <h2>
              {g.name} <br />
              {g.surname}
            </h2>
            <div className="identity">
              ⌖ {g.city}
              <b>{years(g.age)}</b>
            </div>
            <div className="job-badge">
              {job?.name || "Без профессии"}
              {g.job && ` · ур. ${g.careerLevel}`}
            </div>
            <div className="balance">
              <small>ЛИКВИДНЫЕ НАДЕЖДЫ</small>
              <strong>{cash(g.money)}</strong>
              {g.debt > 0 && (
                <span className="danger">Долг: {cash(g.debt)}</span>
              )}
            </div>
            <div className="stats">
              {Object.entries(g.stats).map(([k, v]) => (
                <div
                  className={`stat ${k === "stress" ? "stress" : ""}`}
                  key={k}
                >
                  <div>
                    <span>{labels[k as keyof Stats]}</span>
                    <b key={v}>{v}</b>
                  </div>
                  <div className="meter">
                    <i style={{ width: `${Math.max(0, v)}%` }} />
                  </div>
                </div>
              ))}
            </div>
            <small className="traits-label">ЗАВОДСКИЕ ДЕФЕКТЫ</small>
            <div className="traits">
              {g.traits.map((t) => (
                <span key={t}>{t}</span>
              ))}
            </div>
            <div className="autosave">● Автосохранение · локально</div>
          </aside>
          <section className="main-column">
            <nav className="tabs" aria-label="Разделы игры">
              {tabs.map(([id, name]) => (
                <button
                  key={id}
                  className={tab === id ? "active" : ""}
                  onClick={() => {
                    beep();
                    setTab(id);
                  }}
                >
                  {name}
                </button>
              ))}
            </nav>
            {g.dead && (
              <section className="death panel">
                <div className="eyebrow danger">
                  FATAL ERROR / HUMAN PROCESS TERMINATED
                </div>
                <h1>И всё.</h1>
                <h2>{ending?.name || "Жизнь завершена"}</h2>
                <p>{ending?.description || g.lastResult}</p>
                <div className="death-summary">
                  {g.age} лет · {g.turn} решений · {g.achievements.length}{" "}
                  достижений
                </div>
                <button
                  className="primary"
                  onClick={() => void run(() => s.newGame())}
                >
                  ЕЩЁ ОДНА ПОПЫТКА ↗
                </button>
              </section>
            )}
            {tab === "life" && (
              <>
                {event && (
                  <section className="event panel" key={event.id}>
                    <div className="event-top">
                      <span className="category">{event.category}</span>
                      <span>
                        ХОД {String(g.turn + 1).padStart(3, "0")} / {g.age} ЛЕТ
                      </span>
                    </div>
                    <EventArtwork category={event.category} />
                    <div className="event-icon">
                      {eventSymbol(event.category)}
                    </div>
                    <div className="eyebrow">СУДЬБА ПРИСЛАЛА УВЕДОМЛЕНИЕ</div>
                    <h1>{event.title}</h1>
                    <p className="event-description">{event.description}</p>
                    <div className="decision-label">
                      ВАШЕ РЕШЕНИЕ <span>КАЖДЫЙ ВЫБОР — ГОД ЖИЗНИ</span>
                    </div>
                    <div className="choices">
                      {event.choices.map((c, i) => (
                        <button
                          key={i}
                          disabled={busy}
                          onClick={() => void run(() => s.choose(i))}
                        >
                          <b>0{i + 1}</b>
                          <span>{c.text}</span>
                          <i aria-hidden="true">→</i>
                        </button>
                      ))}
                    </div>
                    <p className="event-note">
                      Последствия записываются в историю. Некоторые вернутся
                      позже.
                    </p>
                  </section>
                )}
                {g.lastResult && (
                  <section className="result panel" aria-live="polite">
                    <small>↳ ПОСЛЕДСТВИЯ</small>
                    <p>{g.lastResult}</p>
                    {changes.length > 0 && (
                      <div className="outcome-deltas">
                        {changes.map((c) => (
                          <span key={c}>{c}</span>
                        ))}
                      </div>
                    )}
                  </section>
                )}
                {!g.dead && (
                  <section className="quick panel">
                    <div className="section-label">
                      ВЗЯТЬ ЖИЗНЬ В СВОИ РУКИ <span>+1 ГОД</span>
                    </div>
                    <div className="quick-grid">
                      {(["work", "rest", "study", "social"] as const).map(
                        (a, i) => (
                          <button
                            disabled={
                              busy || (a === "work" && (!g.job || g.age < 18))
                            }
                            key={a}
                            onClick={() => act({ type: a })}
                          >
                            <span>{["▣", "☕", "◈", "✦"][i]}</span>
                            {
                              [
                                "Поработать",
                                "Отдохнуть",
                                "Учиться",
                                "Общаться",
                              ][i]
                            }
                          </button>
                        ),
                      )}
                    </div>
                  </section>
                )}
                <div className="news-strip">
                  <span>НОВОСТИ СИМУЛЯЦИИ</span>
                  <p>{newsFor(g)}</p>
                </div>
              </>
            )}
            {tab === "career" && (
              <section className="panel content-panel">
                <div className="eyebrow">РЫНОК ТРУДА / ЧЕЛОВЕК КАК РЕСУРС</div>
                <h1>Продать своё время</h1>
                <p>
                  Зарплата указана за месяц и начисляется за год. Каждое
                  действие тратит год жизни. Работа сверхурочно повышает доход и
                  стресс.
                </p>
                <div className="cards">
                  {JOBS.map((j) => (
                    <article className="item-card" key={j.id}>
                      <div className="item-icon">▣</div>
                      <h3>{j.name}</h3>
                      <strong>{cash(j.salary)} / мес</strong>
                      <p>
                        Интеллект ≥ {j.intellect} · харизма ≥ {j.charisma}
                        <br />
                        Риск: {j.risk}
                      </p>
                      <button
                        disabled={
                          g.dead ||
                          busy ||
                          g.age < 18 ||
                          g.job === j.id ||
                          g.stats.intellect < j.intellect ||
                          g.stats.charisma < j.charisma
                        }
                        onClick={() => act({ type: "job", id: j.id })}
                      >
                        {g.job === j.id ? "✓ Вы работаете здесь" : "Устроиться"}{" "}
                        ↗
                      </button>
                    </article>
                  ))}
                </div>
              </section>
            )}
            {tab === "assets" && (
              <section className="panel content-panel">
                <div className="eyebrow">СОБСТВЕННОСТЬ / НОВЫЕ ПРОБЛЕМЫ</div>
                <h1>Нажитое непосильным</h1>
                <p>
                  Активы требуют содержания и открывают события. Кредит — деньги
                  сейчас, проценты потом.
                </p>
                <div className="finance">
                  <button
                    disabled={g.dead || busy || g.age < 18 || g.debt > 0}
                    onClick={() => act({ type: "loan", amount: 100000 })}
                  >
                    Кредит +100 000 ₽
                  </button>
                  <button
                    disabled={g.dead || busy || g.debt <= 0 || g.money <= 0}
                    onClick={() =>
                      act({ type: "repay", amount: Math.min(g.debt, g.money) })
                    }
                  >
                    Погасить доступную часть долга
                  </button>
                </div>
                <div className="cards">
                  {PROPERTIES.map((p) => (
                    <article key={p.id} className="item-card">
                      <div className="item-icon">⌂</div>
                      <h3>{p.name}</h3>
                      <strong>{cash(p.price)}</strong>
                      <p>
                        Доход: {cash(p.income)} / мес
                        <br />
                        Содержание: {cash(p.maintenance)} / мес
                      </p>
                      <button
                        disabled={
                          g.dead ||
                          busy ||
                          g.age < 18 ||
                          g.properties.includes(p.id) ||
                          g.money < p.price
                        }
                        onClick={() => act({ type: "buy", id: p.id })}
                      >
                        {g.properties.includes(p.id)
                          ? "✓ В собственности"
                          : "Приобрести ↗"}
                      </button>
                    </article>
                  ))}
                </div>
              </section>
            )}
            {tab === "people" && (
              <section className="panel content-panel">
                <div className="eyebrow">СОЦИАЛЬНЫЙ ГРАФ / ВСЁ СЛОЖНО</div>
                <h1>Люди вокруг</h1>
                <p>
                  Близкие помнят поступки. Общайтесь и принимайте решения в
                  событиях.
                </p>
                <div className="cards">
                  {g.relationships.map((r, i) => (
                    <article className="item-card" key={i}>
                      <div className="item-icon">☺</div>
                      <h3>{r.name}</h3>
                      <span className="category">{r.role}</span>
                      <p>Близость: {r.bond}/100</p>
                      <div className="meter">
                        <i style={{ width: `${r.bond}%` }} />
                      </div>
                      {r.memory.slice(-3).map((m, n) => (
                        <p key={n}>↳ {m}</p>
                      ))}
                    </article>
                  ))}
                </div>
                {!g.relationships.length && (
                  <div className="empty">
                    Пока вы знакомы только с экзистенциальным ужасом.
                  </div>
                )}
                {!g.dead && (
                  <div className="relationship-actions">
                    <button
                      className="primary"
                      disabled={busy}
                      onClick={() => act({ type: "social" })}
                    >
                      ВЫЙТИ К ЛЮДЯМ · +1 ГОД
                    </button>
                    <button
                      disabled={
                        busy ||
                        g.age < 18 ||
                        !g.relationships.some(
                          (r) =>
                            (r.role === "партнёр" || r.role === "супруг") &&
                            r.bond >= 65,
                        )
                      }
                      onClick={() => act({ type: "intimacy" })}
                    >
                      БЛИЗОСТЬ · +1 ГОД
                    </button>
                    <p>
                      Взаимное согласие, совершеннолетие и близость не менее 65
                      с партнёром или супругом. Интимная жизнь остаётся за
                      кадром.
                    </p>
                  </div>
                )}
              </section>
            )}
            {tab === "history" && (
              <section className="panel content-panel">
                <div className="eyebrow">ЛОГ СИСТЕМЫ / НИЧЕГО НЕ ЗАБЫТО</div>
                <h1>Личное дело</h1>
                <div className="timeline">
                  {[...g.history].reverse().map((h, i) => (
                    <article key={i}>
                      <span>{h.age} ЛЕТ</span>
                      <div>
                        <h3>{h.title}</h3>
                        <p>{h.text}</p>
                      </div>
                    </article>
                  ))}
                </div>
                {!g.history.length && <p>Биография пока чиста. Ненадолго.</p>}
              </section>
            )}
            {tab === "stats" && (
              <section className="panel content-panel">
                <div className="eyebrow">ОТЧЁТ О ПОТРАЧЕННОЙ ЖИЗНИ</div>
                <h1>Цифры не утешают</h1>
                <div className="summary-grid">
                  {[
                    ["Прожито лет", g.age],
                    ["Принято решений", g.turn],
                    ["Уникальных событий", g.seen.length],
                    [
                      "Достижения",
                      `${g.achievements.length} / ${ACHIEVEMENTS.length}`,
                    ],
                    ["Имущество", g.properties.length],
                    ["Социальные связи", g.relationships.length],
                    ["Уровень карьеры", g.careerLevel],
                    ["Капитал", cash(g.money)],
                    ["Долг", cash(g.debt)],
                  ].map(([l, v]) => (
                    <article key={l}>
                      <small>{l}</small>
                      <strong>{v}</strong>
                    </article>
                  ))}
                </div>
                <h3>Следы решений</h3>
                <div className="flags">
                  <span>
                    Важных поступков:{" "}
                    {Object.values(g.flags).filter((v) => v !== 0).length}
                  </span>
                  <span>Сохранённых воспоминаний: {g.history.length}</span>
                  <span>Рабочий стаж: {g.flags.work || 0}</span>
                </div>
                <p className="muted">
                  Скрытые характеристики влияют на события и концовку.
                </p>
              </section>
            )}
            {tab === "achievements" && (
              <section className="panel content-panel">
                <div className="eyebrow">
                  ДОКАЗАТЕЛЬСТВА СОМНИТЕЛЬНОГО УСПЕХА
                </div>
                <h1>
                  Зал славы{" "}
                  <span className="muted">
                    {g.achievements.length}/{ACHIEVEMENTS.length}
                  </span>
                </h1>
                <div className="cards">
                  {ACHIEVEMENTS.map((a) => (
                    <article
                      className={`item-card achievement ${g.achievements.includes(a.id) ? "unlocked" : "locked"}`}
                      key={a.id}
                    >
                      <div className="item-icon">
                        {g.achievements.includes(a.id) ? "★" : "◇"}
                      </div>
                      <h3>{a.name}</h3>
                      <p>{a.description}</p>
                      <small>
                        {g.achievements.includes(a.id)
                          ? "ПОЛУЧЕНО"
                          : "ЕЩЁ ВПЕРЕДИ"}
                      </small>
                    </article>
                  ))}
                </div>
              </section>
            )}
            {tab === "settings" && (
              <section className="panel content-panel">
                <div className="eyebrow">КОНФИГУРАЦИЯ СИМУЛЯЦИИ</div>
                <h1>Настройки</h1>
                <label className="setting">
                  <span>
                    <b>Звуковые сигналы</b>
                    <small>Тихие звуки действий</small>
                  </span>
                  <input
                    type="checkbox"
                    checked={s.settings.sound}
                    onChange={(e) => s.setSettings({ sound: e.target.checked })}
                  />
                </label>
                <label className="setting">
                  <span>
                    <b>Анимации интерфейса</b>
                    <small>Переходы и изменение характеристик</small>
                  </span>
                  <input
                    type="checkbox"
                    checked={s.settings.animations}
                    onChange={(e) =>
                      s.setSettings({ animations: e.target.checked })
                    }
                  />
                </label>
                <h3>Управление жизнью</h3>
                <p>
                  Сохранение хранится в IndexedDB этого браузера. Экспортируйте
                  JSON для резервной копии.
                </p>
                <div className="save-grid">
                  <button
                    onClick={() =>
                      void run(() => s.save(), "Сохранено. Судьба закреплена.")
                    }
                  >
                    ↓ Сохранить
                  </button>
                  <button
                    onClick={() =>
                      void run(() => s.load(), "Сохранение загружено")
                    }
                  >
                    ↻ Загрузить
                  </button>
                  <button onClick={exportGame}>↗ Экспорт JSON</button>
                  <button onClick={() => file.current?.click()}>
                    ↙ Импорт JSON
                  </button>
                  <button
                    onClick={() => {
                      if (
                        confirm(
                          "Начать новую жизнь? Текущий прогресс будет заменён.",
                        )
                      )
                        void run(() => s.newGame());
                    }}
                  >
                    ＋ Новая жизнь
                  </button>
                  <button
                    className="danger-button"
                    onClick={() => {
                      if (confirm("Удалить сохранение и сбросить прогресс?"))
                        void run(() => s.reset(), "Сохранение удалено");
                    }}
                  >
                    × Сбросить прогресс
                  </button>
                </div>
              </section>
            )}
          </section>
          <aside className="right-column">
            <section className="panel compact">
              <div className="section-label">ОБЪЕКТИВНАЯ РЕАЛЬНОСТЬ</div>
              <span className="big-symbol">⌁</span>
              <h3>
                {g.age < 18
                  ? "Детство — пробный период."
                  : g.age < 60
                    ? "Взрослая жизнь активирована."
                    : "Гарантийный срок истёк."}
              </h3>
              <p>
                {g.age < 18
                  ? "Даже ваши ошибки пока оплачивают другие. Наслаждайтесь."
                  : g.age < 60
                    ? "Теперь за ошибки платите вы. И иногда банк."
                    : "Опыт есть. Инструкция всё ещё не найдена."}
              </p>
              <div className="tiny-line">
                ВРЕМЯ НЕ ОБРАТИТЬ <span>↗</span>
              </div>
            </section>
            <section className="panel compact">
              <div className="section-label">СЛЕД БАБОЧКИ</div>
              <h3>Прошлое умеет ждать.</h3>
              <p>{rumorFor(g)}</p>
              <div className="butterfly">⋈</div>
            </section>
            <section className="panel compact">
              <div className="section-label">ПОСЛЕДНИЕ ЗАПИСИ</div>
              {g.history
                .slice(-3)
                .reverse()
                .map((h, i) => (
                  <div className="mini-history" key={i}>
                    <span>{h.age} лет</span>
                    <p>{h.title}</p>
                  </div>
                ))}
              {!g.history.length && (
                <p>Судьба ещё не испортила ваш послужной список.</p>
              )}
            </section>
          </aside>
        </main>
      )}
      <input
        type="file"
        accept="application/json,.json"
        ref={file}
        hidden
        onChange={(e) => void importGame(e.target.files?.[0])}
      />
      {(notice || s.error) && (
        <div className="notification" role="status">
          <span>{notice || s.error}</span>
          <button
            aria-label="Закрыть уведомление"
            onClick={() => {
              setNotice("");
              useGameStore.setState({ error: "" });
            }}
          >
            ×
          </button>
        </div>
      )}
      {toast && (
        <div className="achievement-toast" role="status">
          <small>★ ДОСТИЖЕНИЕ ПОЛУЧЕНО</small>
          <strong>{toast}</strong>
          <button aria-label="Закрыть достижение" onClick={() => setToast("")}>
            ×
          </button>
        </div>
      )}
      <footer>
        <span>HUMAN.EXE © 2026</span>
        <span>ВСЕ СОВПАДЕНИЯ С ВАШЕЙ ЖИЗНЬЮ — ТРЕВОЖНЫЙ ЗВОНОК.</span>
        <span>18+</span>
      </footer>
    </div>
  );
}
