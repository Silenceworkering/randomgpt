"use strict";
const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => [...root.querySelectorAll(s)];
const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const money = (n) => new Intl.NumberFormat("ru-RU").format(n) + " ₽";
const icons = {
  cpu: "▣",
  gpu: "▤",
  motherboard: "▦",
  ram: "▥",
  ssd: "▰",
  psu: "◈",
  case: "▯",
  cooler: "✺",
};
const labels = {
  socket: "Сокет",
  memory_types: "Типы памяти CPU",
  cores: "Ядра",
  threads: "Потоки",
  power_w: "Расчётное потребление, Вт",
  igpu: "Встроенная графика",
  score: "Оценка VOLTRIX",
  igpu_score: "Оценка встроенной графики",
  memory_type: "Тип памяти",
  form_factor: "Форм-фактор",
  ram_slots: "Слоты памяти",
  max_ram_gb: "Максимум памяти, ГБ",
  m2_nvme: "M.2 NVMe",
  supported_cpus: "CPU в каталоге",
  bios_note: "Примечание BIOS",
  capacity_gb: "Объём, ГБ",
  modules: "Модули",
  speed_mt: "Скорость, МТ/с",
  part_number: "Артикул",
  vram_gb: "Видеопамять, ГБ",
  length_mm: "Длина, мм",
  width_slots: "Занимаемые слоты",
  pcie_8pin: "Разъёмы PCIe 8-pin",
  interface: "Интерфейс",
  wattage: "Мощность, Вт",
  efficiency: "Сертификат",
  board_forms: "Платы",
  max_gpu_mm: "Макс. длина GPU, мм",
  max_gpu_slots: "Слоты корпуса",
  max_cooler_mm: "Макс. высота кулера, мм",
  psu_form: "Формат БП",
  max_psu_mm: "Макс. длина БП, мм",
  sockets: "Сокеты",
  height_mm: "Высота, мм",
  thermal_budget_w: "Тепловой запас VOLTRIX, Вт",
};
const state = {
  items: [],
  byId: {},
  categories: {},
  metadata: {},
  parts: {},
  prices: {},
  compare: [],
  saved: [],
  category: "cpu",
  search: "",
  sort: "price-asc",
  quotes: {},
  result: null,
  evaluation: null,
  checkVersion: 0,
  route: "/",
};
let toastTimer;
function toast(text) {
  $("#toast").textContent = text;
  $("#toast").classList.add("visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => $("#toast").classList.remove("visible"), 4500);
}
function storageRead(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}
function storageWrite(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
    return true;
  } catch {
    toast("Браузер не разрешил сохранение. Экспортируйте сборку в файл.");
    return false;
  }
}
async function api(path, body) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 65000);
  try {
    const response = await fetch(path, {
      method: body ? "POST" : "GET",
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });
    const data = await response.json();
    if (!response.ok)
      throw new Error(
        typeof data.detail === "string"
          ? data.detail
          : "Проверьте параметры запроса. Бюджет: 15 000–500 000 ₽; цены: 1–2 000 000 ₽.",
      );
    return data;
  } catch (error) {
    if (error.name === "AbortError")
      throw new Error(
        "Сервис долго отвечает. Бесплатный Render может просыпаться около минуты. Попробуйте ещё раз.",
      );
    if (error instanceof TypeError)
      throw new Error(
        "Нет соединения с сервисом. Проверьте интернет и повторите запрос.",
      );
    throw error;
  } finally {
    clearTimeout(timer);
  }
}
function valueText(value, key) {
  if (value === null || value === undefined) return "—";
  if (typeof value === "boolean") return value ? "Да" : "Нет";
  if (Array.isArray(value))
    return value
      .map((v) => (key === "supported_cpus" ? state.byId[v]?.name || v : v))
      .join(", ");
  return String(value);
}
function brief(item) {
  const s = item.specs;
  return {
    cpu: `${s.cores} ядер / ${s.threads} потоков · ${s.socket}`,
    gpu: `${s.vram_gb} ГБ · ${s.power_w} Вт · ${s.length_mm} мм`,
    motherboard: `${s.socket} · ${s.memory_type} · ${s.form_factor}`,
    ram: `${s.capacity_gb} ГБ · ${s.memory_type} · ${s.speed_mt} МТ/с`,
    ssd: `${s.capacity_gb} ГБ · ${s.interface}`,
    psu: `${s.wattage} Вт · ${s.efficiency}`,
    case: `${(s.board_forms || []).join(" / ")} · GPU до ${s.max_gpu_mm} мм`,
    cooler: `${s.height_mm} мм · ${(s.sockets || []).join(" / ")}`,
  }[item.category];
}
function pageHead(kicker, title, description) {
  return `<div class="page-head"><div class="eyebrow"><span class="live-dot"></span>${kicker}</div><h1>${title}</h1><p class="subtitle">${description}</p></div>`;
}
function priceNotice() {
  return `<div class="notice">${esc(state.metadata.price_notice)}</div>`;
}
function errorMarkup(message) {
  return `<div class="error-box" role="alert">${esc(message)}</div>`;
}
function emptyMarkup(title, description, link, label) {
  return `<div class="empty"><div class="feature-icon">ϟ</div><h3>${title}</h3><p>${description}</p>${link ? `<a class="button" href="${link}" data-route>${label} →</a>` : ""}</div>`;
}
function loading(text = "Подбираем совместимые комплектующие…") {
  return `<div class="loading-screen"><span class="loader"></span>${text}</div>`;
}
function openModal(title, html) {
  $("#modal-title").textContent = title;
  $("#modal-content").innerHTML = html;
  if (!$("#modal").open) $("#modal").showModal();
}
function closeModal() {
  $("#modal").close();
}
function updateCompareCount() {
  $("#compare-count").textContent = state.compare.length;
}
function addCompare(id) {
  const item = state.byId[id];
  if (!item) return;
  if (state.compare.includes(id)) {
    state.compare = state.compare.filter((x) => x !== id);
    toast("Модель убрана из сравнения.");
  } else {
    if (
      state.compare.length &&
      state.byId[state.compare[0]].category !== item.category
    ) {
      toast(
        "Сравнивайте модели одной категории. Очистите предыдущий список в разделе «Сравнение».",
      );
      return;
    }
    if (state.compare.length >= 4) {
      toast("Можно сравнить до четырёх моделей.");
      return;
    }
    state.compare.push(id);
    toast("Добавлено к сравнению.");
  }
  storageWrite("voltrix.compare.v1", state.compare);
  updateCompareCount();
  $$(`[data-compare="${id}"]`).forEach((b) => {
    b.classList.toggle("selected", state.compare.includes(id));
    b.setAttribute("aria-pressed", String(state.compare.includes(id)));
  });
  if (state.route === "/compare") renderCompare();
}
function addPart(id) {
  const item = state.byId[id];
  if (!item) return;
  state.parts[item.category] = id;
  persistDraft();
  closeModal();
  navigate("/configurator");
  toast("Компонент добавлен в сборку.");
}
function persistDraft() {
  storageWrite("voltrix.draft.v1", {
    components: state.parts,
    price_overrides: state.prices,
  });
}
function currentPrice(item) {
  return state.prices[item.id] ?? item.estimate_rub;
}
function renderHome() {
  $("#main").innerHTML =
    `<div class="page-enter"><section class="hero"><div class="hero-copy"><div class="eyebrow"><span class="live-dot"></span>ТВОЯ СЛЕДУЮЩАЯ СБОРКА НАЧИНАЕТСЯ ЗДЕСЬ</div><h1>ТВОЙ ПК.<br><span class="gradient-text">ТВОИ ПРАВИЛА.</span></h1><p class="hero-description">От первой детали до идеальной сборки.<br>Подбирай комплектующие, проверяй совместимость<br>и находи свой баланс цены и мощности.</p><div class="actions"><a class="button" href="/configurator" data-route>Собрать свой ПК <span>→</span></a><a class="button secondary" href="/smart" data-route><span>✧</span> Подобрать под бюджет</a></div><div class="hero-note"><span>Бесплатно</span><span>Без регистрации</span><span>Проверка совместимости</span></div></div><div class="hero-art"><img src="/static/pc.svg" alt="Чёрный системный блок VOLTRIX с фиолетовой подсветкой" width="620" height="620"><div class="art-tag">Точность в каждой детали<strong>✓ Совместимость под контролем</strong></div><span class="art-label">СОЗДАН ДЛЯ ТВОЕГО СЛЕДУЮЩЕГО УРОВНЯ</span></div></section>
 <div class="summary-strip"><div><b>${state.items.length}</b><span>реальных моделей<br>в стартовом каталоге</span></div><div><b>8</b><span>категорий<br>комплектующих</span></div><div><b>12</b><span>правил проверки<br>совместимости</span></div><div><b>0 ₽</b><span>за подбор<br>твоей сборки</span></div></div>
 <section class="section"><div class="smart-banner"><div><span class="feature-icon">✧</span><div class="eyebrow">УМНЫЙ ПОДБОР · БЕЗ МАГИИ</div><h2>Бюджет твой. Подбор наш.</h2><p class="subtitle">Укажи сумму и задачу — алгоритм найдёт совместимую сборку с лучшей оценкой в нашем каталоге.</p><p class="micro">Примерные цены для расчёта. Проверяй предложения магазинов перед покупкой.</p></div><form id="quick-form" class="quick-form"><label class="field">Твой бюджет, ₽<input name="budget" type="number" min="15000" max="500000" step="1000" value="80000" required></label><label class="field">Для чего нужен ПК?<select name="purpose"><option value="gaming">Игры</option><option value="work">Работа и творчество</option><option value="office">Офис и учёба</option></select></label><button class="button" type="submit">Найти мою сборку <span>→</span></button></form></div></section>
 <section class="section"><div class="section-head"><div><div class="eyebrow">ОТПРАВНАЯ ТОЧКА</div><h2>Три задачи. Три подхода.</h2><p class="subtitle">Подборки рассчитываются из каталога при открытии.</p></div><a class="text-link" href="/smart" data-route>Все возможности →</a></div><div class="build-grid">${[
   [
     "gaming",
     "ИГРОВОЙ",
     "Для твоих побед",
     "Приоритет видеокарте и сбалансированной платформе.",
     80000,
   ],
   [
     "work",
     "РАБОЧИЙ",
     "Для больших идей",
     "Больше внимания процессору, памяти и накопителю.",
     110000,
   ],
   [
     "office",
     "ПОВСЕДНЕВНЫЙ",
     "Для каждого дня",
     "Учёба, офис и браузер. Только нужная мощность.",
     45000,
   ],
 ]
   .map(
     ([purpose, badge, title, desc, budget]) =>
       `<article class="preset-card"><div class="preset-image"><img src="/static/pc.svg" alt="" loading="lazy" width="210" height="210"><span class="badge">${badge}</span></div><div class="preset-info"><h3>${title}</h3><p>${desc}</p><div class="preset-bottom"><b>до ${money(budget)}</b><button class="button small secondary" data-preset="${purpose}" data-budget="${budget}">Подобрать →</button></div></div></article>`,
   )
   .join("")}</div></section>
 <section class="section"><div class="section-head"><div><div class="eyebrow">ПРОЩЕ, ЧЕМ КАЖЕТСЯ</div><h2>От идеи до готовой сборки</h2></div></div><div class="steps"><article class="step"><span class="step-number">01 / ВЫБЕРИ</span><h3>Детали, которые подходят тебе</h3><p>Изучи характеристики и сравни до четырёх моделей. Открой поиск у продавцов, чтобы проверить цены.</p></article><article class="step"><span class="step-number">02 / ПРОВЕРЬ</span><h3>Пусть всё работает вместе</h3><p>Сокеты, тип памяти, мощность и размеры. Конфигуратор покажет ошибки и подскажет, что проверить.</p></article><article class="step"><span class="step-number">03 / СОХРАНИ</span><h3>Твоя сборка всегда под рукой</h3><p>Сохрани в этом браузере или экспортируй в файл. Вернись к сборке, когда будешь готов к покупке.</p></article></div></section></div>`;
  $("#quick-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    navigate("/smart");
    $("#smart-budget").value = form.get("budget");
    $("#smart-purpose").value = form.get("purpose");
    $("#smart-form").requestSubmit();
  });
  $$("[data-preset]").forEach((b) =>
    b.addEventListener("click", () => {
      navigate("/smart");
      $("#smart-budget").value = b.dataset.budget;
      $("#smart-purpose").value = b.dataset.preset;
      $("#smart-form").requestSubmit();
    }),
  );
}
function productCard(item) {
  return `<article class="product-card"><div class="product-visual" aria-hidden="true">${icons[item.category]}</div><span class="brand">${esc(item.brand)}</span><h3>${esc(item.name)}</h3><p class="spec-summary">${esc(brief(item))}</p><div class="product-price">~${money(item.estimate_rub)}</div><span class="price-label">Примерная цена · не предложение магазина</span><div class="product-actions"><button class="button secondary" data-detail="${item.id}">Подробнее →</button><button class="button ghost" data-add="${item.id}">+ В сборку</button><button class="icon-button" data-compare="${item.id}" aria-label="Сравнить ${esc(item.name)}" aria-pressed="${state.compare.includes(item.id)}" title="Сравнить">⇄</button></div></article>`;
}
function renderCatalog() {
  $("#main").innerHTML =
    `<div class="page-enter">${pageHead("КОМПЛЕКТУЮЩИЕ", "Найди свою деталь.", "Реальные модели, понятные характеристики и поиск предложений у продавцов.")}${priceNotice()}<div class="catalog-layout"><aside class="categories" aria-label="Категории каталога">${Object.entries(
      state.categories,
    )
      .map(
        ([key, name]) =>
          `<button class="category-btn ${state.category === key ? "active" : ""}" data-category="${key}" aria-pressed="${state.category === key}"><span>${icons[key]}</span>${name}<small>${state.items.filter((i) => i.category === key).length}</small></button>`,
      )
      .join(
        "",
      )}</aside><section><div class="toolbar"><input class="search-input" id="catalog-search" type="search" aria-label="Поиск модели" placeholder="Название, бренд или артикул…" value="${esc(state.search)}"><select id="catalog-sort" aria-label="Сортировка"><option value="price-asc">Сначала дешевле</option><option value="price-desc">Сначала дороже</option><option value="name">По названию</option></select></div><div id="catalog-results"></div><p class="source-note">Характеристики справочные. Точная ревизия, BIOS, QVL и наличие требуют проверки. Оценки VOLTRIX не являются бенчмарками.</p></section></div></div>`;
  $("#catalog-sort").value = state.sort;
  $$("[data-category]").forEach((b) =>
    b.addEventListener("click", () => {
      state.category = b.dataset.category;
      renderCatalog();
    }),
  );
  $("#catalog-search").addEventListener("input", (e) => {
    state.search = e.target.value;
    renderCatalogResults();
  });
  $("#catalog-sort").addEventListener("change", (e) => {
    state.sort = e.target.value;
    renderCatalogResults();
  });
  renderCatalogResults();
}
function filteredItems(category, search) {
  const query = search.trim().toLocaleLowerCase("ru-RU");
  return state.items.filter(
    (i) =>
      (!category || i.category === category) &&
      `${i.name} ${i.brand} ${i.specs.part_number || ""}`
        .toLocaleLowerCase("ru-RU")
        .includes(query),
  );
}
function renderCatalogResults() {
  let items = filteredItems(state.category, state.search);
  items.sort((a, b) =>
    state.sort === "name"
      ? a.name.localeCompare(b.name, "ru")
      : state.sort === "price-desc"
        ? b.estimate_rub - a.estimate_rub
        : a.estimate_rub - b.estimate_rub,
  );
  $("#catalog-results").innerHTML =
    `<p class="filters-note">${esc(state.categories[state.category])} · найдено ${items.length}</p>${items.length ? `<div class="product-grid">${items.map(productCard).join("")}</div>` : emptyMarkup("Ничего не найдено", "Попробуйте другое название или категорию.")}`;
  bindProducts($("#catalog-results"));
}
function bindProducts(root) {
  $$("[data-detail]", root).forEach((b) =>
    b.addEventListener("click", () => detail(b.dataset.detail)),
  );
  $$("[data-add]", root).forEach((b) =>
    b.addEventListener("click", () => addPart(b.dataset.add)),
  );
  $$("[data-compare]", root).forEach((b) =>
    b.addEventListener("click", () => addCompare(b.dataset.compare)),
  );
}
function detail(id) {
  const item = state.byId[id];
  openModal(
    item.name,
    `<div class="badge">${esc(state.categories[item.category])}</div><p class="subtitle">${esc(brief(item))}</p><div class="detail-specs">${Object.entries(
      item.specs,
    )
      .map(
        ([k, v]) =>
          `<div><span>${esc(labels[k] || k)}</span><b>${esc(valueText(v, k))}</b></div>`,
      )
      .join(
        "",
      )}</div><div class="product-price">~${money(item.estimate_rub)}<span class="price-label">Примерная расчётная цена. Актуальные предложения здесь не загружаются.</span></div><div class="actions"><button class="button" data-add="${id}">+ Добавить в сборку</button><button class="button secondary" data-compare="${id}" aria-pressed="${state.compare.includes(id)}">⇄ Сравнить</button></div><h3>Проверить цены у продавцов</h3><p class="micro">Ссылки открывают поиск модели. Сверьте точный артикул, наличие и цену на сайте магазина.</p><div class="store-links">${item.stores.map((store) => `<a class="button small ghost" href="${esc(store.url)}" target="_blank" rel="noopener noreferrer">${esc(store.name)} →</a>`).join("")}${item.manufacturer_url ? `<a class="button small ghost" href="${esc(item.manufacturer_url)}" target="_blank" rel="noopener noreferrer">Производитель →</a>` : ""}</div><section class="manual-prices"><h3>Сравнить найденные цены</h3><p class="micro">Откройте поиск у продавцов и введите найденные суммы. Это ваши записи, не автоматическая загрузка актуальных предложений. Доставка не учитывается.</p><div class="quotes-grid">${item.stores.map((store, index) => `<label class="field">${esc(store.name)}, ₽<input type="number" min="1" max="2000000" step="1" data-quote="${index}" value="${state.quotes[id]?.[index] || ""}" placeholder="Цена из магазина"></label>`).join("")}</div><p class="micro" id="best-quote"></p><button class="button small secondary" id="apply-quote">Применить лучшую цену к расчёту</button></section><p class="source-note">${esc(state.metadata.spec_notice)}</p>`,
  );
  bindProducts($("#modal-content"));
  bindQuotes(item);
}
function bindQuotes(item) {
  const id = item.id;
  const entries = () =>
    Object.entries(state.quotes[id] || {})
      .filter(([, price]) => Number.isInteger(price) && price > 0)
      .sort((a, b) => a[1] - b[1]);
  const render = () => {
    const all = entries();
    $("#best-quote").textContent = all.length
      ? `Минимум из ваших записей: ${money(all[0][1])} — ${item.stores[Number(all[0][0])].name}. Проверяйте цену перед покупкой.`
      : "Введите цены, чтобы сравнить предложения.";
  };
  $$("[data-quote]").forEach((input) =>
    input.addEventListener("change", () => {
      const key = input.dataset.quote;
      if (!state.quotes[id]) state.quotes[id] = {};
      if (input.value === "") {
        delete state.quotes[id][key];
      } else {
        const value = Number(input.value);
        if (!Number.isInteger(value) || value < 1 || value > 2000000) {
          toast("Цена должна быть целой: от 1 до 2 000 000 ₽.");
          input.value = state.quotes[id][key] || "";
          return;
        }
        state.quotes[id][key] = value;
      }
      storageWrite("voltrix.quotes.v1", state.quotes);
      render();
    }),
  );
  $("#apply-quote").addEventListener("click", () => {
    const all = entries();
    if (!all.length) {
      toast("Сначала введите найденную цену хотя бы одного магазина.");
      return;
    }
    state.prices[id] = all[0][1];
    persistDraft();
    toast("Ваша минимальная цена применена к конфигуратору и подбору.");
    if (state.route === "/configurator") renderConfigurator();
  });
  render();
}
function picker(category) {
  openModal(
    state.categories[category],
    `<input type="search" class="search-input" id="picker-search" aria-label="Поиск компонента" placeholder="Найти модель…"><p class="micro">Все модели доступны для выбора. После добавления конфигуратор проверит совместимость.</p><div class="modal-grid" id="picker-list"></div>`,
  );
  const render = () => {
    const items = filteredItems(category, $("#picker-search").value);
    $("#picker-list").innerHTML =
      items
        .map(
          (item) =>
            `<article class="modal-item"><h3>${esc(item.name)}</h3><p>${esc(brief(item))}</p><p>~${money(currentPrice(item))} · ${state.prices[item.id] ? "ваша цена" : "примерная цена"}</p><button class="button small secondary" data-add="${item.id}">Выбрать +</button></article>`,
        )
        .join("") || '<p class="subtitle">Модель не найдена.</p>';
    bindProducts($("#picker-list"));
  };
  $("#picker-search").addEventListener("input", render);
  render();
}
function componentRow(category) {
  const item = state.byId[state.parts[category]];
  return `<article class="component-row ${item ? "" : "empty-row"}"><div class="component-icon" aria-hidden="true">${icons[category]}</div><div class="component-body"><div class="category-label">${esc(state.categories[category])}${category === "gpu" ? " · не нужна при встроенной графике" : ""}</div><h3>${item ? esc(item.name) : "Выберите компонент"}</h3>${item ? `<p class="spec-summary">${esc(brief(item))}</p>` : ""}</div>${item ? `<label class="component-price"><input type="number" min="1" max="2000000" step="1" value="${currentPrice(item)}" data-price="${item.id}" aria-label="Цена ${esc(item.name)}, рублей"><small>${state.prices[item.id] ? "Ваша цена, ₽" : "Примерная цена, ₽"}</small></label>` : ""}<div class="component-buttons"><button class="button ghost" data-pick="${category}">${item ? "Заменить" : "Добавить +"}</button>${item ? `<button class="icon-button" data-remove="${category}" aria-label="Убрать ${esc(state.categories[category])}">×</button>` : ""}</div></article>`;
}
function renderConfigurator() {
  $("#main").innerHTML =
    `<div class="page-enter">${pageHead("КОНФИГУРАТОР ПК", "Собери свой следующий уровень.", "Выбирай детали в любом порядке. Мы проверим совместимость и посчитаем бюджет.")}${priceNotice()}<div class="toolbar"><button class="button small secondary" id="save-build">Сохранить сборку ↓</button><button class="button small ghost" id="export-build">Экспорт JSON</button><button class="button small ghost" id="share-build">Ссылка на состав →</button><button class="button small ghost" id="reset-prices">Сбросить мои цены</button><button class="button small danger" id="clear-build">Очистить сборку</button></div><div class="config-layout"><section class="component-list">${Object.keys(state.categories).map(componentRow).join("")}</section><aside class="config-summary" id="config-summary">${loading("Проверяем сборку…")}</aside></div><p class="source-note">Проверка по данным стартового каталога не заменяет проверку CPU Support List, QVL, ревизии и комплекта креплений. Сборки хранятся только в этом браузере.</p></div>`;
  $$("[data-pick]").forEach((b) =>
    b.addEventListener("click", () => picker(b.dataset.pick)),
  );
  $$("[data-remove]").forEach((b) =>
    b.addEventListener("click", () => {
      delete state.parts[b.dataset.remove];
      persistDraft();
      renderConfigurator();
    }),
  );
  $$("[data-price]").forEach((input) =>
    input.addEventListener("change", () => {
      const n = Number(input.value);
      if (!Number.isInteger(n) || n < 1 || n > 2000000) {
        toast("Введите целую цену от 1 до 2 000 000 ₽.");
        input.value = currentPrice(state.byId[input.dataset.price]);
        return;
      }
      state.prices[input.dataset.price] = n;
      persistDraft();
      input.nextElementSibling.textContent = "Ваша цена, ₽";
      checkBuild();
    }),
  );
  $("#save-build").addEventListener("click", saveDialog);
  $("#export-build").addEventListener("click", () => exportBuild());
  $("#share-build").addEventListener("click", shareBuild);
  $("#reset-prices").addEventListener("click", () => {
    state.prices = {};
    persistDraft();
    renderConfigurator();
    toast("Возвращены примерные цены каталога.");
  });
  $("#clear-build").addEventListener("click", () =>
    confirmDialog(
      "Очистить сборку?",
      "Текущий состав и введённые цены будут очищены. Сохранённые сборки останутся.",
      () => {
        state.parts = {};
        state.prices = {};
        persistDraft();
        renderConfigurator();
      },
    ),
  );
  checkBuild();
}
async function checkBuild() {
  const version = ++state.checkVersion;
  try {
    const evaluation = await api("/api/build/check", {
      components: { ...state.parts },
      price_overrides: { ...state.prices },
    });
    if (version !== state.checkVersion) return;
    state.evaluation = evaluation;
    if (state.route === "/configurator" && $("#config-summary"))
      renderSummary(evaluation);
  } catch (error) {
    if (version === state.checkVersion && $("#config-summary")) {
      $("#config-summary").innerHTML =
        errorMarkup(error.message) +
        '<button class="button small" id="retry-check">Повторить проверку</button>';
      $("#retry-check").addEventListener("click", checkBuild);
    }
  }
}
function renderSummary(e) {
  const c = e.compatibility;
  $("#config-summary").innerHTML =
    `<h2>Твоя сборка</h2><span class="total-label">${Object.keys(e.components).length} из 8 категорий · сумма для расчёта</span><div class="total">${money(e.total_rub)}</div><span class="price-label">${Object.values(e.components).some((i) => i.user_price) ? "Есть введённые вами цены. Остальные — примерные." : "Все цены примерные, не актуальные предложения."}</span><div class="compatibility-status ${c.errors.length ? "error" : ""}">${c.errors.length ? "✕ Есть несовместимые компоненты" : c.complete ? "✓ Сборка прошла проверки" : "◷ Заверши сборку для полной проверки"}</div>${c.estimated_power_w ? `<p class="micro">Оценка потребления: ${c.estimated_power_w} Вт<br>БП с запасом: от ${c.recommended_psu_w} Вт</p>` : ""}<div class="check-list">${c.checks.map((check) => `<div class="check ${check.status}"><span>${check.status === "ok" ? "✓" : check.status === "error" ? "✕" : "◷"}</span><span>${esc(check.message)}</span></div>`).join("")}</div>${c.missing.length ? `<p class="micro">Осталось добавить: ${esc(c.missing.join(", "))}.</p>` : ""}${c.warnings.map((w) => `<p class="warning">⚠ ${esc(w)}</p>`).join("")}<div class="actions"><button class="button" id="summary-save">Сохранить сборку ↓</button><a class="button secondary" href="/smart" data-route>Доверить подбор алгоритму ✧</a></div>`;
  $("#summary-save").addEventListener("click", saveDialog);
}
function renderSmart() {
  $("#main").innerHTML =
    `<div class="page-enter">${pageHead("БЕСПЛАТНЫЙ АЛГОРИТМ", "Мощность в рамках бюджета.", "Перебираем совместимые комбинации и выбираем лучшую оценку для твоей задачи. Без платных AI API.")}${priceNotice()}<div class="smart-layout"><form class="smart-form" id="smart-form"><h2>Настрой подбор</h2><label class="field">Бюджет, ₽<input id="smart-budget" name="budget" type="number" min="15000" max="500000" step="1" value="80000" required><span>От 15 000 до 500 000 ₽</span></label><label class="field">Назначение<select name="purpose" id="smart-purpose"><option value="gaming">Игры</option><option value="work">Работа и творчество</option><option value="office">Офис и учёба</option></select></label><label class="field">Процессор<select name="cpu_brand"><option value="any">Без предпочтений</option><option value="AMD">AMD</option><option value="Intel">Intel</option></select></label><label class="field">Видеокарта<select name="gpu_brand"><option value="any">Без предпочтений</option><option value="NVIDIA">NVIDIA</option><option value="AMD">AMD Radeon</option></select></label><button class="button" type="submit">Подобрать мой ПК <span>✧</span></button><p class="micro">${Object.keys(state.prices).length ? "В расчёте используются также ваши цены из конфигуратора." : "Подбор использует примерные цены каталога. Свои цены можно задать в конфигураторе."}<br>Периферия, ОС и доставка не входят в бюджет. Для специфичного ПО проверьте системные требования.</p></form><section class="smart-result" id="smart-result">${state.result ? resultMarkup(state.result) : emptyMarkup("Твоя сборка появится здесь", "Выбери бюджет, задачу и бренды.<br>Мы позаботимся о совместимости.")}</section></div></div>`;
  $("#smart-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = e.currentTarget;
    const data = new FormData(form);
    const button = $("button[type=submit]", form);
    button.disabled = true;
    button.textContent = "Подбираем…";
    $("#smart-result").innerHTML = loading();
    try {
      const result = await api("/api/recommend", {
        budget: Number(data.get("budget")),
        purpose: data.get("purpose"),
        cpu_brand: data.get("cpu_brand"),
        gpu_brand: data.get("gpu_brand"),
        price_overrides: { ...state.prices },
      });
      state.result = result;
      if (state.route === "/smart" && $("#smart-result")) {
        $("#smart-result").innerHTML = resultMarkup(result);
        bindResult();
      }
    } catch (error) {
      if (state.route === "/smart" && $("#smart-result"))
        $("#smart-result").innerHTML = errorMarkup(error.message);
    } finally {
      button.disabled = false;
      button.innerHTML = "Подобрать мой ПК <span>✧</span>";
    }
  });
  if (state.result) bindResult();
}
function resultMarkup(result) {
  return `<div class="result-head"><div><div class="eyebrow">ПОДБОР ЗАВЕРШЁН</div><h2>Можно собирать.</h2><p>Все компоненты прошли проверки.<br>Остаток бюджета: ${money(result.remaining_rub)}</p></div><b>~${money(result.total_rub)}</b></div><div>${Object.entries(
    result.components,
  )
    .map(
      ([category, item]) =>
        `<div class="result-row"><div><span>${esc(state.categories[category])}</span><strong>${esc(item.name)}</strong></div><b>${item.user_price ? "" : "~"}${money(item.calculation_rub)}</b></div>`,
    )
    .join(
      "",
    )}</div><div class="actions"><button class="button" id="use-result">Открыть в конфигураторе →</button><button class="button secondary" id="save-result">Сохранить ↓</button></div><div class="explanation"><h3>Почему эта сборка?</h3><ul>${result.explanation.map((s) => `<li>${esc(s)}</li>`).join("")}</ul><p>Оценка для задачи: ${result.score}. Расчёт БП: от ${result.compatibility.recommended_psu_w} Вт.</p>${result.compatibility.warnings.map((w) => `<p class="warning">⚠ ${esc(w)}</p>`).join("")}<p class="micro">Цены для расчёта: ${Object.values(result.components).some((i) => i.user_price) ? "смешанные (ваши и примерные)" : "примерные"}. Проверяйте точные цены и наличие у продавцов.</p></div>`;
}
function applyResult() {
  state.parts = Object.fromEntries(
    Object.entries(state.result.components).map(([k, v]) => [k, v.id]),
  );
  state.prices = Object.fromEntries(
    Object.values(state.result.components)
      .filter((i) => i.user_price)
      .map((i) => [i.id, i.calculation_rub]),
  );
  persistDraft();
}
function bindResult() {
  $("#use-result")?.addEventListener("click", () => {
    applyResult();
    navigate("/configurator");
  });
  $("#save-result")?.addEventListener("click", () => {
    applyResult();
    saveDialog();
  });
}
async function renderCompare() {
  $("#main").innerHTML =
    `<div class="page-enter">${pageHead("СРАВНЕНИЕ ХАРАКТЕРИСТИК", "Решай на основе деталей.", "От двух до четырёх моделей одной категории. Различия выделены фиолетовым.")}${priceNotice()}<div class="compare-tools"><a class="button small secondary" href="/catalog" data-route>+ Выбрать в каталоге</a><button class="button small ghost" id="clear-compare">Очистить сравнение</button><label class="inline-label"><input type="checkbox" id="only-different"> Только различия</label></div><div id="compare-result">${state.compare.length >= 2 ? loading("Сравниваем характеристики…") : emptyMarkup("Добавь модели для сравнения", state.compare.length ? "Выбрана одна модель. Добавь ещё одну из той же категории." : "Открой каталог и нажми ⇄ на карточках.", "/catalog", "Перейти в каталог")}</div></div>`;
  $("#clear-compare").addEventListener("click", () => {
    state.compare = [];
    storageWrite("voltrix.compare.v1", []);
    updateCompareCount();
    renderCompare();
  });
  $("#only-different").addEventListener("change", (e) =>
    $$("tr.same").forEach((row) => (row.hidden = e.target.checked)),
  );
  const snapshot = state.compare.join(",");
  if (state.compare.length < 2) return;
  try {
    const data = await api("/api/compare", { ids: state.compare });
    if (state.route !== "/compare" || snapshot !== state.compare.join(","))
      return;
    $("#compare-result").innerHTML =
      `<div class="compare-wrap"><table><thead><tr><th>Характеристика</th>${data.items.map((i) => `<th><div class="compare-name"><button class="icon-button" data-compare="${i.id}" aria-label="Удалить ${esc(i.name)}">×</button>${esc(i.name)}</div><span class="price-label">~${money(i.estimate_rub)} · примерная цена</span><button class="button small secondary" data-detail="${i.id}">Магазины и детали →</button></th>`).join("")}</tr></thead><tbody>${data.rows
        .map((row) => {
          const different =
            new Set(row.values.map((v) => JSON.stringify(v))).size > 1;
          return `<tr class="${different ? "different" : "same"}"><td>${esc(labels[row.key] || row.key)}</td>${row.values.map((v) => `<td>${esc(valueText(v, row.key))}</td>`).join("")}</tr>`;
        })
        .join("")}</tbody></table></div>`;
    bindProducts($("#compare-result"));
    if ($("#only-different").checked)
      $$("tr.same").forEach((row) => (row.hidden = true));
  } catch (error) {
    if (state.route === "/compare")
      $("#compare-result").innerHTML = errorMarkup(error.message);
  }
}
function validBuild(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const components = raw.components;
  const prices = raw.price_overrides || {};
  if (
    !components ||
    typeof components !== "object" ||
    Array.isArray(components) ||
    typeof prices !== "object" ||
    Array.isArray(prices)
  )
    return null;
  if (
    Object.entries(components).some(
      ([k, v]) =>
        typeof v !== "string" ||
        !Object.hasOwn(state.categories, k) ||
        !Object.hasOwn(state.byId, v) ||
        state.byId[v].category !== k,
    )
  )
    return null;
  if (
    Object.entries(prices).some(
      ([k, v]) =>
        !Object.hasOwn(state.byId, k) ||
        !Number.isInteger(v) ||
        v < 1 ||
        v > 2000000,
    )
  )
    return null;
  return { components: { ...components }, price_overrides: { ...prices } };
}
function buildRecord(name) {
  return {
    version: 1,
    id: crypto.randomUUID(),
    name: name.trim().slice(0, 80) || "Моя сборка",
    created_at: new Date().toISOString(),
    components: { ...state.parts },
    price_overrides: { ...state.prices },
  };
}
function saveDialog() {
  if (!Object.keys(state.parts).length) {
    toast("Сначала добавьте хотя бы один компонент.");
    return;
  }
  openModal(
    "Сохранить сборку",
    `<form class="save-form" id="save-form"><label class="field">Название<input name="name" maxlength="80" value="Мой VOLTRIX" required autofocus></label><p class="subtitle">Сборка останется в этом браузере. Для переноса на другой телефон экспортируй JSON. Можно сохранять и незавершённые сборки.</p><button class="button" type="submit">Сохранить ↓</button></form>`,
  );
  $("#save-form").addEventListener("submit", (e) => {
    e.preventDefault();
    if (state.saved.length >= 50) {
      toast("Сохранено 50 сборок. Экспортируйте и удалите ненужные.");
      return;
    }
    const record = buildRecord(new FormData(e.currentTarget).get("name"));
    const next = [record, ...state.saved];
    if (storageWrite("voltrix.saved.v1", next)) {
      state.saved = next;
      closeModal();
      toast("Сборка сохранена в этом браузере.");
      if (state.route === "/saved") renderSaved();
    }
  });
}
function downloadJSON(record) {
  const blob = new Blob([JSON.stringify(record, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "voltrix-build.json";
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function exportBuild(record) {
  if (!record && !Object.keys(state.parts).length) {
    toast("Добавьте компоненты перед экспортом.");
    return;
  }
  downloadJSON(record || buildRecord("Моя сборка"));
}
async function shareBuild() {
  if (!Object.keys(state.parts).length) {
    toast("Добавьте компоненты перед созданием ссылки.");
    return;
  }
  const url = new URL("/configurator", location.origin);
  url.searchParams.set("parts", Object.values(state.parts).join(","));
  try {
    await navigator.clipboard.writeText(url.href);
    toast("Ссылка на состав скопирована. Введённые цены в неё не входят.");
  } catch {
    openModal(
      "Ссылка на состав",
      `<label class="field">Скопируйте ссылку<input readonly value="${esc(url.href)}" id="share-url"></label><p class="micro">Ссылка передаёт состав без ваших цен. Для переноса цен используйте экспорт JSON.</p>`,
    );
    $("#share-url").select();
  }
}
function confirmDialog(title, description, action) {
  openModal(
    title,
    `<p class="subtitle">${esc(description)}</p><div class="actions toolbar"><button class="button danger" id="confirm-action">Подтвердить</button><button class="button secondary" id="cancel-action">Отмена</button></div>`,
  );
  $("#confirm-action").addEventListener("click", () => {
    closeModal();
    action();
  });
  $("#cancel-action").addEventListener("click", closeModal);
}
function recordTotal(record) {
  return Object.values(record.components).reduce(
    (sum, id) =>
      sum + (record.price_overrides[id] ?? state.byId[id].estimate_rub),
    0,
  );
}
function renderSaved() {
  $("#main").innerHTML =
    `<div class="page-enter">${pageHead("ЛИЧНАЯ КОЛЛЕКЦИЯ", "Твои сборки. Твои планы.", "Сборки хранятся в localStorage этого браузера. Очистка данных браузера удалит их — сохраняй резервную копию JSON.")}<div class="toolbar"><a class="button small" href="/configurator" data-route>+ Новая сборка</a><button class="button small secondary" id="import-build">Импорт JSON ↑</button><input type="file" accept=".json,application/json" id="import-file" hidden></div><div class="saved-grid">${state.saved
      .map(
        (record) =>
          `<article class="saved-card"><span class="date">${esc(new Date(record.created_at).toLocaleDateString("ru-RU"))} · ${Object.keys(record.components).length} компонентов</span><h2>${esc(record.name)}</h2><div class="saved-parts">${Object.values(
            record.components,
          )
            .map((id) => esc(state.byId[id].name))
            .join(
              "<br>",
            )}</div><div class="product-price">~${money(recordTotal(record))}<span class="price-label">По сохранённым ценам и расчётным ценам каталога</span></div><div class="actions"><button class="button secondary" data-load="${record.id}">Открыть →</button><button class="button ghost" data-export="${record.id}">Экспорт ↓</button><button class="button danger" data-delete="${record.id}">Удалить</button></div></article>`,
      )
      .join(
        "",
      )}</div>${!state.saved.length ? emptyMarkup("Начало твоей коллекции", "Здесь появятся сохранённые сборки.<br>Собери ПК или импортируй файл JSON.", "/configurator", "Создать сборку") : ""}</div>`;
  $("#import-build").addEventListener("click", () => $("#import-file").click());
  $("#import-file").addEventListener("change", importFile);
  $$("[data-load]").forEach((b) =>
    b.addEventListener("click", () => {
      const record = state.saved.find((r) => r.id === b.dataset.load);
      state.parts = { ...record.components };
      state.prices = { ...record.price_overrides };
      persistDraft();
      navigate("/configurator");
    }),
  );
  $$("[data-export]").forEach((b) =>
    b.addEventListener("click", () =>
      exportBuild(state.saved.find((r) => r.id === b.dataset.export)),
    ),
  );
  $$("[data-delete]").forEach((b) =>
    b.addEventListener("click", () =>
      confirmDialog(
        "Удалить сохранённую сборку?",
        "Она будет удалена из этого браузера. Экспортированная копия останется.",
        () => {
          const next = state.saved.filter((r) => r.id !== b.dataset.delete);
          if (storageWrite("voltrix.saved.v1", next)) {
            state.saved = next;
            renderSaved();
          }
        },
      ),
    ),
  );
}
async function importFile(e) {
  const file = e.target.files[0];
  if (!file) return;
  try {
    if (file.size > 200000)
      throw new Error("Файл слишком большой. Максимум 200 КБ.");
    const raw = JSON.parse(await file.text());
    const build = validBuild(raw);
    if (
      !raw ||
      raw.version !== 1 ||
      !build ||
      !Object.keys(build.components).length
    )
      throw new Error(
        "Неверный формат VOLTRIX JSON или неизвестные компоненты.",
      );
    if (state.saved.length >= 50) throw new Error("Достигнут лимит 50 сборок.");
    const record = {
      version: 1,
      ...build,
      id: crypto.randomUUID(),
      name:
        typeof raw.name === "string"
          ? raw.name.slice(0, 80)
          : "Импортированная сборка",
      created_at: new Date().toISOString(),
    };
    const next = [record, ...state.saved];
    if (storageWrite("voltrix.saved.v1", next)) {
      state.saved = next;
      renderSaved();
      toast("Сборка импортирована. Проверка доступна при открытии.");
    }
  } catch (error) {
    toast(
      error instanceof SyntaxError
        ? "Не удалось прочитать JSON. Проверьте файл."
        : error.message,
    );
  } finally {
    e.target.value = "";
  }
}
function renderAbout() {
  $("#main").innerHTML =
    `<div class="page-enter">${pageHead("О ПРОЕКТЕ", "Больше ясности. Больше VOLTRIX.", "Российский проект для осознанной сборки ПК. Бесплатная первая версия с прозрачными правилами.")}<div class="about-grid"><article class="about-card"><div class="eyebrow">НАША ИДЕЯ</div><h2>Хороший ПК начинается с правильных вопросов.</h2><p>Сколько ты готов потратить? Что будешь делать? Какие детали работают вместе? VOLTRIX помогает пройти этот путь без регистрации и платных сервисов.</p><h3>Как работает умный подбор</h3><p>Алгоритм перебирает совместимые связки процессора, платы, памяти, видеокарты и SSD. Для каждой выбирает самые недорогие подходящие корпус, кулер и БП. Из сборок в пределах бюджета выбирает наибольшую оценку для задачи, а при равенстве — меньшую цену.</p><p>Игровая оценка: 30% CPU, 65% GPU, бонусы памяти и SSD, штраф за дисбаланс. Рабочая: 65% CPU, 20% GPU и повышенные бонусы памяти и SSD. Офисная ограничивает пользу избыточной мощности. Баллы относительные, назначены в каталоге и не означают FPS. Поиск оптимален в рамках этой модели и каталога.</p><h3>Что проверяется</h3><p>Сокет и поддержка CPU, тип и объём памяти, размеры платы, видеокарты и кулера, крепление и тепловой запас охлаждения, мощность и разъёмы БП, интерфейс SSD и наличие графики.</p><p>Мощность БП: потребление CPU + GPU + 60 Вт для остального, затем 35% запаса и округление вверх до 50 Вт. Это консервативная оценка, не измерение энергопотребления.</p></article><article class="about-card"><div class="eyebrow">ЧЕСТНО О ПЕРВОЙ ВЕРСИИ</div><h2>Данные, которым нужен контекст.</h2><h3>Цены и магазины</h3><p>В каталоге реальные модели и примерные расчётные цены. Актуальные цены и наличие автоматически не загружаются. Ссылки в карточках открывают поиск в DNS, Ситилинке и Яндекс Маркете. Сравни предложения на их сайтах, введи цены в карточке модели и примени минимальную к расчёту. Также цену можно задать в конфигураторе.</p><h3>Совместимость</h3><p>${esc(state.metadata.spec_notice)}</p><h3>Хранение сборок</h3><p>Сборки, черновик и введённые цены сохраняются в localStorage браузера. Нет аккаунтов и синхронизации. Экспортируй JSON для резервной копии или переноса. В Telegram пользовательские сборки не хранятся.</p><h3>Telegram и доступность</h3><p>Бот использует тот же Python-модуль подбора. Команда: <code>/build 80000 gaming AMD NVIDIA</code>. Адрес конкретного бота задаётся владельцем проекта при развёртывании.</p><p>На бесплатном Render сервис может засыпать. Первый запрос иногда ждёт около минуты; Telegram может повторить webhook. Подбор бесплатный, внешний AI не используется.</p><div class="actions"><a class="button small" href="/smart" data-route>Попробовать подбор →</a><a class="button small ghost" href="/docs" target="_blank" rel="noopener">Документация API →</a></div></article></div></div>`;
}
const routes = {
  "/": renderHome,
  "/catalog": renderCatalog,
  "/configurator": renderConfigurator,
  "/smart": renderSmart,
  "/compare": renderCompare,
  "/saved": renderSaved,
  "/about": renderAbout,
};
function renderRoute() {
  state.route = location.pathname;
  const fn = routes[state.route] || renderHome;
  fn();
  $$(".desktop-nav a").forEach((a) =>
    a.classList.toggle("active", a.getAttribute("href") === state.route),
  );
  $("#mobile-nav").hidden = true;
  $("#menu-button").setAttribute("aria-expanded", "false");
  const titles = {
    "/": "Твой ПК, твои правила",
    "/catalog": "Каталог",
    "/configurator": "Конфигуратор ПК",
    "/smart": "Умный подбор",
    "/compare": "Сравнение",
    "/saved": "Мои сборки",
    "/about": "О проекте",
  };
  document.title = "VOLTRIX — " + (titles[state.route] || titles["/"]);
}
function navigate(path) {
  history.pushState({}, "", path);
  renderRoute();
  window.scrollTo({ top: 0, behavior: "instant" });
  $("#main").focus({ preventScroll: true });
}
function loadSharedParts() {
  const ids = new URLSearchParams(location.search).get("parts");
  if (!ids) return;
  const parts = {};
  for (const id of ids.split(",").slice(0, 8)) {
    if (Object.hasOwn(state.byId, id)) parts[state.byId[id].category] = id;
  }
  if (Object.keys(parts).length) {
    state.parts = parts;
    state.prices = {};
    persistDraft();
    toast("Состав загружен по ссылке. Цены — примерные.");
  }
}
async function init() {
  try {
    const data = await api("/api/catalog");
    state.items = data.items;
    state.byId = Object.fromEntries(data.items.map((i) => [i.id, i]));
    state.categories = data.categories;
    state.metadata = data.metadata;
    const quotes = storageRead("voltrix.quotes.v1", {});
    if (quotes && typeof quotes === "object" && !Array.isArray(quotes)) {
      for (const [id, values] of Object.entries(quotes)) {
        if (
          !Object.hasOwn(state.byId, id) ||
          !values ||
          typeof values !== "object" ||
          Array.isArray(values)
        )
          continue;
        state.quotes[id] = Object.fromEntries(
          Object.entries(values).filter(
            ([key, value]) =>
              ["0", "1", "2"].includes(key) &&
              Number.isInteger(value) &&
              value > 0 &&
              value <= 2000000,
          ),
        );
      }
    }
    const draft = validBuild(storageRead("voltrix.draft.v1", {}));
    if (draft) {
      state.parts = draft.components;
      state.prices = draft.price_overrides;
    }
    const compare = storageRead("voltrix.compare.v1", []);
    if (Array.isArray(compare)) {
      state.compare = [
        ...new Set(compare.filter((id) => Object.hasOwn(state.byId, id))),
      ].slice(0, 4);
      if (state.compare.length)
        state.compare = state.compare.filter(
          (id) =>
            state.byId[id].category === state.byId[state.compare[0]].category,
        );
    }
    const saved = storageRead("voltrix.saved.v1", []);
    if (Array.isArray(saved))
      state.saved = saved
        .filter(
          (r) =>
            validBuild(r) &&
            typeof r.name === "string" &&
            typeof r.id === "string" &&
            /^[a-zA-Z0-9-]{1,80}$/.test(r.id) &&
            !Number.isNaN(Date.parse(r.created_at)),
        )
        .slice(0, 50)
        .map((r) => ({ ...r, name: r.name.slice(0, 80) }));
    loadSharedParts();
    updateCompareCount();
    renderRoute();
  } catch (error) {
    $("#main").innerHTML =
      `<div class="page-head">${errorMarkup(error.message)}<button class="button toolbar" id="retry-init">Повторить загрузку</button></div>`;
    $("#retry-init").addEventListener("click", init);
  }
}
document.addEventListener("click", (e) => {
  const link = e.target.closest("a[data-route]");
  if (
    !link ||
    e.ctrlKey ||
    e.metaKey ||
    e.shiftKey ||
    e.altKey ||
    e.button !== 0
  )
    return;
  e.preventDefault();
  if (!state.items.length) {
    toast("Сначала дождитесь загрузки каталога.");
    return;
  }
  navigate(link.getAttribute("href"));
});
$("#menu-button").addEventListener("click", () => {
  const nav = $("#mobile-nav");
  nav.hidden = !nav.hidden;
  $("#menu-button").setAttribute("aria-expanded", String(!nav.hidden));
});
$("#close-modal").addEventListener("click", closeModal);
$("#modal").addEventListener("click", (e) => {
  if (e.target === $("#modal")) {
    const rect = e.target.getBoundingClientRect();
    if (
      e.clientX < rect.left ||
      e.clientX > rect.right ||
      e.clientY < rect.top ||
      e.clientY > rect.bottom
    )
      closeModal();
  }
});
window.addEventListener("popstate", () => {
  if (state.items.length) {
    loadSharedParts();
    renderRoute();
  }
});
init();
