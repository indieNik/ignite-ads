/* IgniteAds landing — Three.js particle stream + GSAP scroll narrative.
   Degrades gracefully: reduced-motion users get a static page; the WebGL
   scene caps DPR, thins out on mobile, and pauses when offscreen/hidden. */

const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const isMobile = window.matchMedia("(max-width: 820px)").matches;

/* ============================== hero particle stream ============================== */
async function initStream() {
  if (reduceMotion) return;
  const canvas = document.getElementById("stream");
  try {
    const THREE = await import("https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js");

    const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: false });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, isMobile ? 1.5 : 2));

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(50, 1, 0.1, 50);
    camera.position.z = 7;

    const COUNT = isMobile ? 1600 : 4200;
    const seeds = new Float32Array(COUNT * 4);
    for (let i = 0; i < COUNT; i++) {
      seeds[i * 4 + 0] = Math.random();            // progress offset along stream
      seeds[i * 4 + 1] = Math.random() * 2 - 1;    // lane (y spread)
      seeds[i * 4 + 2] = Math.random() * 2 - 1;    // depth
      seeds[i * 4 + 3] = 0.4 + Math.random() * 0.9; // speed/size factor
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(new Float32Array(COUNT * 3), 3));
    geo.setAttribute("seed", new THREE.BufferAttribute(seeds, 4));

    const mat = new THREE.ShaderMaterial({
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      uniforms: { uTime: { value: 0 }, uPointer: { value: new THREE.Vector2(0, 0) }, uFade: { value: 1 } },
      vertexShader: `
        attribute vec4 seed;
        uniform float uTime;
        uniform vec2 uPointer;
        varying float vX;
        varying float vAlpha;
        void main() {
          float span = 16.0;
          float x = mod(seed.x * span + uTime * seed.w * 1.4, span) - span * 0.5;
          float curve = sin(x * 0.45 + seed.y * 2.0) * 0.55;
          float y = seed.y * 1.5 + curve + sin(uTime * 0.7 + seed.x * 40.0) * 0.07;
          float z = seed.z * 2.2;
          // gentle pointer parallax
          y += uPointer.y * 0.35 * seed.z;
          x += uPointer.x * 0.4 * seed.z;
          vec4 mv = modelViewMatrix * vec4(x, y, z, 1.0);
          gl_Position = projectionMatrix * mv;
          gl_PointSize = (seed.w * 3.4) * (6.0 / -mv.z);
          vX = (x + span * 0.5) / span;
          // fade at stream edges
          vAlpha = smoothstep(0.0, 0.12, vX) * (1.0 - smoothstep(0.85, 1.0, vX));
        }`,
      fragmentShader: `
        uniform float uFade;
        varying float vX;
        varying float vAlpha;
        void main() {
          vec2 uv = gl_PointCoord - 0.5;
          float d = length(uv);
          float disc = smoothstep(0.5, 0.1, d);
          vec3 purple = vec3(0.427, 0.290, 1.0);
          vec3 pink   = vec3(1.0, 0.290, 0.831);
          vec3 cyan   = vec3(0.290, 0.831, 1.0);
          vec3 col = vX < 0.5 ? mix(purple, pink, vX * 2.0) : mix(pink, cyan, vX * 2.0 - 1.0);
          gl_FragColor = vec4(col, disc * vAlpha * 0.75 * uFade);
        }`,
    });
    scene.add(new THREE.Points(geo, mat));

    function resize() {
      const w = canvas.clientWidth, h = canvas.clientHeight;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    }
    resize();
    window.addEventListener("resize", resize);

    const pointer = { x: 0, y: 0 };
    window.addEventListener("pointermove", (e) => {
      pointer.x = (e.clientX / window.innerWidth) * 2 - 1;
      pointer.y = -(e.clientY / window.innerHeight) * 2 + 1;
    }, { passive: true });

    let visible = true, hidden = false;
    new IntersectionObserver(([e]) => { visible = e.isIntersecting; }).observe(canvas);
    document.addEventListener("visibilitychange", () => { hidden = document.hidden; });

    const clock = new (class { t = 0; last = performance.now(); tick() { const n = performance.now(); this.t += (n - this.last) / 1000; this.last = n; return this.t; } })();
    (function loop() {
      requestAnimationFrame(loop);
      if (!visible || hidden) { clock.last = performance.now(); return; }
      mat.uniforms.uTime.value = clock.tick();
      mat.uniforms.uPointer.value.x += (pointer.x - mat.uniforms.uPointer.value.x) * 0.04;
      mat.uniforms.uPointer.value.y += (pointer.y - mat.uniforms.uPointer.value.y) * 0.04;
      renderer.render(scene, camera);
    })();

    // fade the stream as the hero scrolls away
    if (window.gsap) {
      gsap.to(mat.uniforms.uFade, {
        value: 0, ease: "none",
        scrollTrigger: { trigger: ".hero", start: "40% top", end: "bottom top", scrub: true },
      });
    }
  } catch (e) {
    console.warn("WebGL stream unavailable:", e);
    canvas.style.background = "radial-gradient(60% 50% at 50% 45%, rgba(109,74,255,.18), transparent 70%)";
  }
}

/* ============================== GSAP narrative ============================== */
function initMotion() {
  if (!window.gsap || reduceMotion) return;
  gsap.registerPlugin(ScrollTrigger);

  // nav border on scroll
  ScrollTrigger.create({
    start: 40, onUpdate: (self) => document.getElementById("nav").classList.toggle("scrolled", self.scroll() > 40),
  });

  // hero headline: per-char rise (explicit two-line split — keeps the <em> gradient)
  // line 1: per-char rise; line 2: whole-line masked rise (background-clip:text
  // doesn't survive per-char child spans in Chromium, so the <em> stays intact)
  const title = document.getElementById("hero-title");
  const chars = (text) => text.split("").map((c) => c === " " ? " " : `<span class="char">${c}</span>`).join("");
  title.innerHTML = `${chars("Your AI ads,")}<br /><span class="line-mask"><em>actually launched.</em></span>`;
  gsap.from("#hero-title .char", {
    yPercent: 110, opacity: 0, rotateZ: 4,
    duration: 0.9, stagger: 0.022, ease: "expo.out", delay: 0.15,
  });
  gsap.from("#hero-title .line-mask em", {
    yPercent: 115, duration: 1.1, ease: "expo.out", delay: 0.45,
  });
  gsap.from(".hero .eyebrow, .hero-sub, .hero-ctas, .hero-stats", {
    y: 26, opacity: 0, duration: 0.9, stagger: 0.12, ease: "power3.out", delay: 0.55,
  });

  // generic reveal-ups
  document.querySelectorAll(".section .reveal-up").forEach((el) => {
    gsap.from(el, {
      y: 36, opacity: 0, duration: 0.9, ease: "power3.out",
      scrollTrigger: { trigger: el, start: "top 86%" },
    });
  });

  // marquee drift
  gsap.to(".marquee-track", { xPercent: -33.33, ease: "none", duration: 18, repeat: -1 });

  // dead cards drift in
  gsap.from(".dead-card", {
    y: 60, opacity: 0, stagger: 0.15, duration: 1, ease: "power3.out",
    scrollTrigger: { trigger: ".dead-cards", start: "top 80%" },
  });

  // pipeline: progress line + step lighting tied to scroll
  const steps = gsap.utils.toArray(".pipe-step");
  ScrollTrigger.create({
    trigger: ".pipe-wrap", start: "top 70%", end: "bottom 55%", scrub: 0.4,
    onUpdate: (self) => {
      document.getElementById("pipe-progress").style.height = `${self.progress * 100}%`;
      steps.forEach((s, i) => s.classList.toggle("lit", self.progress >= (i + 0.5) / steps.length));
    },
  });

  // safety cards: pointer tilt (desktop only)
  if (!isMobile) {
    document.querySelectorAll(".tilt-card").forEach((card) => {
      card.addEventListener("pointermove", (e) => {
        const r = card.getBoundingClientRect();
        const rx = ((e.clientY - r.top) / r.height - 0.5) * -10;
        const ry = ((e.clientX - r.left) / r.width - 0.5) * 12;
        card.style.transform = `perspective(700px) rotateX(${rx}deg) rotateY(${ry}deg) translateY(-3px)`;
      });
      card.addEventListener("pointerleave", () => { card.style.transform = ""; });
    });

    // magnetic buttons
    document.querySelectorAll(".magnetic").forEach((btn) => {
      btn.addEventListener("pointermove", (e) => {
        const r = btn.getBoundingClientRect();
        gsap.to(btn, { x: (e.clientX - r.left - r.width / 2) * 0.25, y: (e.clientY - r.top - r.height / 2) * 0.35, duration: 0.3 });
      });
      btn.addEventListener("pointerleave", () => gsap.to(btn, { x: 0, y: 0, duration: 0.5, ease: "elastic.out(1, 0.4)" }));
    });
  }

  // final title scale-in
  gsap.from("#final-title", {
    scale: 0.7, opacity: 0, duration: 1.1, ease: "expo.out",
    scrollTrigger: { trigger: ".final", start: "top 75%" },
  });
}

/* ============================== gemini typewriter mock ============================== */
function initTypewriter() {
  const COPY = {
    "tw-primary": "Stop scrolling — your closet called. The bag that pulls every outfit together is one tap away. ✨",
    "tw-headline": "Effortless Style, Every Day",
    "tw-desc": "Carry the moment.",
  };
  const btn = document.getElementById("mock-btn");
  let played = false;

  async function type(id, text) {
    const el = document.getElementById(id);
    for (let i = 1; i <= text.length; i += 2) {
      el.textContent = text.slice(0, i);
      await new Promise((r) => setTimeout(r, 18));
    }
    el.textContent = text;
  }
  async function play() {
    if (played) return;
    played = true;
    btn.classList.add("thinking");
    btn.textContent = "Gemini is writing…";
    await new Promise((r) => setTimeout(r, reduceMotion ? 0 : 900));
    for (const [id, text] of Object.entries(COPY)) {
      if (reduceMotion) document.getElementById(id).textContent = text;
      else await type(id, text);
    }
    btn.classList.remove("thinking");
    btn.textContent = "✨ Suggest with Gemini";
  }

  new IntersectionObserver(([e]) => { if (e.isIntersecting) play(); }, { threshold: 0.5 })
    .observe(document.getElementById("mock-card"));
  btn.addEventListener("click", () => { played = false; play(); });
}

initStream();
initMotion();
initTypewriter();
