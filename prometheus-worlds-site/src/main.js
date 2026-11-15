import "./styles.css";

const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function initNav() {
  const root = document.documentElement;
  const button = document.querySelector(".nav-toggle");
  const nav = document.getElementById("site-nav");
  const label = button.querySelector(".nav-toggle-label");
  if (!button || !nav) return;

  root.classList.add("js");

  const setOpen = (open) => {
    nav.classList.toggle("is-open", open);
    button.setAttribute("aria-expanded", String(open));
    label.textContent = open ? "Close" : "Menu";
    document.body.classList.toggle("nav-open", open);
  };

  button.addEventListener("click", () => {
    const open = button.getAttribute("aria-expanded") !== "true";
    setOpen(open);
    if (open) {
      const first = nav.querySelector("a");
      first?.focus();
    }
  });

  nav.addEventListener("click", (event) => {
    if (event.target.closest("a")) window.setTimeout(() => setOpen(false), 0);
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && button.getAttribute("aria-expanded") === "true") {
      setOpen(false);
      button.focus();
    }
  });
}

function initCurrentSection() {
  const links = [...document.querySelectorAll(".site-nav a")];
  const sections = links
    .map((link) => document.querySelector(link.getAttribute("href")))
    .filter(Boolean);
  if (!sections.length || !("IntersectionObserver" in window)) return;

  const byId = new Map(links.map((link) => [link.getAttribute("href").slice(1), link]));
  const observer = new IntersectionObserver(
    (entries) => {
      const visible = entries
        .filter((entry) => entry.isIntersecting)
        .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
      if (!visible) return;
      for (const link of links) link.removeAttribute("aria-current");
      byId.get(visible.target.id)?.setAttribute("aria-current", "true");
    },
    { rootMargin: "-40% 0px -50% 0px", threshold: [0.1, 0.3, 0.6] },
  );
  for (const section of sections) observer.observe(section);
}

function initHeader() {
  const header = document.querySelector(".site-header");
  if (!header) return;
  const onScroll = () => header.classList.toggle("is-scrolled", window.scrollY > 8);
  onScroll();
  window.addEventListener("scroll", onScroll, { passive: true });
}

function initEmbers() {
  const canvas = document.getElementById("embers");
  if (!canvas || reduceMotion) return;
  const context = canvas.getContext("2d", { alpha: true });
  if (!context) return;

  const hero = canvas.parentElement;
  const count = 42;
  const embers = Array.from({ length: count }, () => spawn(true));
  let frame = 0;
  let running = true;

  function spawn(anywhere) {
    return {
      x: Math.random(),
      y: anywhere ? Math.random() : 1.05,
      r: 0.6 + Math.random() * 2.2,
      speed: 0.00035 + Math.random() * 0.00085,
      drift: (Math.random() - 0.5) * 0.12,
      phase: Math.random() * Math.PI * 2,
      hot: Math.random(),
    };
  }

  function resize() {
    const rect = hero.getBoundingClientRect();
    const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
    canvas.width = Math.max(1, Math.round(rect.width * dpr));
    canvas.height = Math.max(1, Math.round(rect.height * dpr));
    canvas.style.width = `${rect.width}px`;
    canvas.style.height = `${rect.height}px`;
  }

  function draw() {
    if (!running) return;
    frame = requestAnimationFrame(draw);
    const { width, height } = canvas;
    context.clearRect(0, 0, width, height);
    for (const ember of embers) {
      ember.y -= ember.speed * 1.6;
      ember.phase += 0.01;
      if (ember.y < -0.05) Object.assign(ember, spawn(false));
      const x = (ember.x + Math.sin(ember.phase) * ember.drift) * width;
      const y = ember.y * height;
      const radius = ember.r * (width / 1400) * 2.2;
      const alpha = Math.max(0, Math.min(0.85, ember.y * 1.2)) * (0.35 + ember.hot * 0.65);
      const gradient = context.createRadialGradient(x, y, 0, x, y, radius * 4);
      const core = ember.hot > 0.7 ? "255, 214, 170" : "255, 122, 48";
      gradient.addColorStop(0, `rgba(${core}, ${alpha})`);
      gradient.addColorStop(1, `rgba(255, 80, 20, 0)`);
      context.fillStyle = gradient;
      context.beginPath();
      context.arc(x, y, radius * 4, 0, Math.PI * 2);
      context.fill();
    }
  }

  resize();
  const resizeObserver = new ResizeObserver(resize);
  resizeObserver.observe(hero);

  const visibility = new IntersectionObserver(([entry]) => {
    running = entry.isIntersecting && !document.hidden;
    if (running) {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(draw);
    }
  });
  visibility.observe(hero);
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) running = false;
    else if (hero.getBoundingClientRect().bottom > 0) {
      running = true;
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(draw);
    }
  });
  frame = requestAnimationFrame(draw);
}

initNav();
initCurrentSection();
initHeader();
initEmbers();
