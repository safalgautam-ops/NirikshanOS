(() => {
  'use strict';

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const root = document.documentElement;
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;

  function setupSmoothNavigation() {
    $$('a[href^="#"]').forEach((link) => {
      link.addEventListener('click', (event) => {
        const id = link.getAttribute('href');
        if (!id || id === '#') return;
        const target = document.querySelector(id);
        if (!target) return;
        event.preventDefault();
        target.scrollIntoView({ behavior: reducedMotion ? 'auto' : 'smooth', block: 'start' });
        history.replaceState(null, '', id);
      });
    });

  }

  function setupMobileMenu() {
    const nav = document.querySelector('nav');
    const toggle = nav?.querySelector('button[aria-label="Toggle menu"]');
    if (!nav || !toggle) return;

    const panel = document.createElement('div');
    panel.className = 'mobile-menu-panel';
    panel.hidden = true;
    const links = [
      ...$$('[data-header-links] a', nav),
      $('[data-header-cta]', nav),
    ].filter(Boolean);
    panel.replaceChildren(...links.map((source) => {
      const link = document.createElement('a');
      link.href = source.getAttribute('href');
      link.textContent = source.textContent.trim();
      return link;
    }));
    nav.appendChild(panel);

    const bars = [...toggle.querySelectorAll('span')];
    const setOpen = (open) => {
      panel.hidden = !open;
      toggle.setAttribute('aria-expanded', String(open));
      toggle.setAttribute('aria-label', open ? 'Close menu' : 'Toggle menu');
      if (bars[0]) bars[0].style.transform = open ? 'translateY(3px) rotate(45deg)' : '';
      if (bars[1]) bars[1].style.transform = open ? 'translateY(-3px) rotate(-45deg)' : '';
    };

    toggle.addEventListener('click', () => setOpen(panel.hidden));
    panel.addEventListener('click', (event) => {
      if (event.target.closest('a')) setOpen(false);
    });
    addEventListener('resize', () => { if (innerWidth >= 768) setOpen(false); });
    document.addEventListener('pointerdown', (event) => {
      if (!panel.hidden && !nav.contains(event.target)) setOpen(false);
    });
  }

  function setupReveals() {
    const elements = $$('[data-reveal="true"]');
    if (reducedMotion || !('IntersectionObserver' in window)) {
      elements.forEach((el) => el.classList.add('is-visible'));
      return;
    }

    // Words inside the featured testimonial retain the original staggered cadence.
    elements.forEach((el, index) => {
      if (el.tagName === 'SPAN') el.style.transitionDelay = `${Math.min(index * 14, 420)}ms`;
    });

    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add('is-visible');
        observer.unobserve(entry.target);
      });
    }, { rootMargin: '0px 0px -8% 0px', threshold: 0.08 });

    elements.forEach((el) => observer.observe(el));
  }

  function setupCopyAndChat() {
    const input = $('#case-note-message');
    if (!input) return;
    input.addEventListener('keydown', (event) => {
      if (event.key !== 'Enter' || !input.value.trim()) return;
      event.preventDefault();
      const value = input.value.trim();
      input.value = '';
      const composer = input.closest('form')?.parentElement;
      const messageArea = composer?.previousElementSibling;
      if (!messageArea?.classList.contains('no-visible-scrollbar')) return;
      messageArea.classList.remove('overflow-hidden');
      messageArea.classList.add('overflow-y-auto');
      const row = document.createElement('div');
      row.className = 'mb-4 flex gap-2 flex-row';
      row.dataset.chatMessage = 'local';
      row.innerHTML = `<div class="size-8 shrink-0 overflow-hidden rounded-md bg-neutral-100 ring-1 ring-black/10"><img class="size-full object-cover" src="/static/home/assets/images/avatar-AlexClient.webp" alt="Analyst"></div><div class="min-w-0"><div class="flex items-baseline gap-2"><span class="text-xs font-semibold">Analyst</span><span class="text-[10px] text-neutral-400">Now</span></div><p class="mt-1 rounded-xl rounded-tl-sm bg-neutral-100 px-3 py-2 text-xs text-neutral-700">${value.replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}</p></div>`;
      messageArea.appendChild(row);
      messageArea.scrollTop = messageArea.scrollHeight;
    });
  }

  function setupHeroCanvas() {
    const canvas = $('#hero-canvas');
    if (!canvas) return;
    const context = canvas.getContext('2d');
    let width = 0, height = 0, dpr = 1, raf = 0;
    const pointer = { x: 0.5, y: -0.2, tx: 0.5, ty: -0.2 };
    let points = [];

    function resize() {
      const rect = canvas.getBoundingClientRect();
      dpr = Math.min(devicePixelRatio || 1, 2);
      width = Math.max(1, rect.width);
      height = Math.max(1, rect.height);
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      context.setTransform(dpr, 0, 0, dpr, 0, 0);
      const gap = width < 700 ? 20 : 24;
      points = [];
      for (let y = 8; y < height; y += gap) {
        for (let x = 8; x < width; x += gap) {
          points.push({ x, y, phase: Math.random() * Math.PI * 2 });
        }
      }
    }

    function draw(time = 0) {
      context.clearRect(0, 0, width, height);
      pointer.x += (pointer.tx - pointer.x) * 0.05;
      pointer.y += (pointer.ty - pointer.y) * 0.05;
      const px = pointer.x * width;
      const py = pointer.y * height;
      const radius = Math.max(width, height) * 0.36;

      const glow = context.createRadialGradient(px, py, 0, px, py, radius * 1.8);
      glow.addColorStop(0, 'rgba(38,103,255,.10)');
      glow.addColorStop(.55, 'rgba(38,103,255,.035)');
      glow.addColorStop(1, 'rgba(38,103,255,0)');
      context.fillStyle = glow;
      context.fillRect(0, 0, width, height);

      for (const point of points) {
        const distance = Math.hypot(point.x - px, point.y - py);
        const influence = Math.max(0, 1 - distance / radius);
        const pulse = .5 + .5 * Math.sin(time * .0008 + point.phase);
        const alpha = .035 + influence * .28 + pulse * .018;
        const size = .7 + influence * 1.7;
        context.beginPath();
        context.arc(point.x, point.y, size, 0, Math.PI * 2);
        context.fillStyle = `rgba(38,103,255,${alpha})`;
        context.fill();
      }
      if (!reducedMotion) raf = requestAnimationFrame(draw);
    }

    const parent = canvas.parentElement;
    parent?.addEventListener('pointermove', (event) => {
      const rect = canvas.getBoundingClientRect();
      pointer.tx = (event.clientX - rect.left) / rect.width;
      pointer.ty = (event.clientY - rect.top) / rect.height;
    });
    parent?.addEventListener('pointerleave', () => { pointer.tx = .5; pointer.ty = -.2; });
    new ResizeObserver(resize).observe(canvas);
    resize();
    draw();
    addEventListener('pagehide', () => cancelAnimationFrame(raf), { once: true });
  }


  function setupProcessAnimations() {
    const section = $('#process-motion-section');
    if (!section) return;
    const cards = $$('[data-process-card]', section);

    // 1. Figma-like cursor and selection motion.
    const figmaCard = cards[0];
    if (figmaCard) {
      const stage = figmaCard.querySelector('.h-full.w-full.flex.rounded-xl') || figmaCard.querySelector('.relative.z-20');
      if (stage) {
        stage.classList.add('process-figma-stage');
        const cursorIcon = stage.querySelector('svg.size-4.text-neutral-900');
        const cursor = cursorIcon?.closest('.pointer-events-none.absolute');
        cursor?.classList.add('process-figma-cursor');
        if (!stage.querySelector('.process-figma-selection')) {
          const selection = document.createElement('div');
          selection.className = 'process-figma-selection';
          stage.append(selection);
        }
      }
    }

    // 2. Dynamic-island sequence: idle -> connecting -> connected -> idle.
    const idle = $('#idle-content', section);
    const loading = $('#loading-content', section);
    const connected = $('#connected-content', section);
    const island = idle?.parentElement;
    let islandTimer = 0;
    let islandRunning = false;

    if (loading && !loading.querySelector('.process-island-dot')) {
      const dots = document.createElement('div');
      dots.innerHTML = '<i class="process-island-dot"></i><i class="process-island-dot"></i><i class="process-island-dot"></i>';
      loading.replaceChildren(dots);
    }

    const islandState = (state) => {
      if (!island || !idle || !loading || !connected) return;
      const states = { idle, loading, connected };
      Object.entries(states).forEach(([name, node]) => {
        const active = name === state;
        node.style.opacity = active ? '1' : '0';
        node.style.transform = active ? 'none' : 'scale(.96)';
      });
      if (state === 'loading') {
        island.style.width = '20px';
        island.style.height = '12px';
        island.style.borderRadius = '6px';
      } else if (state === 'connected') {
        island.style.width = '50px';
        island.style.height = '12px';
        island.style.borderRadius = '8px';
      } else {
        island.style.width = '36px';
        island.style.height = '12px';
        island.style.borderRadius = '6px';
      }
    };

    function queueIslandCycle() {
      if (!islandRunning || reducedMotion) return;
      islandState('idle');
      islandTimer = window.setTimeout(() => {
        islandState('loading');
        islandTimer = window.setTimeout(() => {
          islandState('connected');
          islandTimer = window.setTimeout(queueIslandCycle, 2300);
        }, 1250);
      }, 1250);
    }

    // 3. Type code, morph to a working slider, then repeat.
    const microCard = cards[2];
    const code = microCard?.querySelector('pre code');
    const shell = code?.closest('.rounded-3xl');
    let microTimer = 0;
    let microRunning = false;
    const tokens = [
      ['<',0],['div',1],['\n  ',0],['role',1],['="slider"',0],['\n  ',0],['className',1],['="relative h-8 w-full rounded-md bg-neutral-800"',0],['\n',0],['>',0],['\n  ',0],['<',0],['motion',1],['.',0],['div',1],['\n    ',0],['className',1],['="absolute inset-y-0 left-0 rounded-l-md bg-neutral-600/90"',0],['\n    ',0],['initial',1],['={false}',0],['\n    ',0],['animate',1],['={{ width: ',0],['`${value * 100}%`',0],[' }}',0],['\n  ',0],['/>',0],['\n  ',0],['<',0],['motion',1],['.',0],['div',1],['\n    ',0],['className',1],['="absolute top-1/2 z-10 h-5 w-3 -translate-x-1/2"',0],['\n    ',0],['animate',1],['={{ left: ',0],['`${value * 100}%`',0],[' }}',0],['\n  ',0],['/>',0],['\n',0],['</',0],['div',1],['>',0]
    ];
    const chars = tokens.flatMap(([text, primary]) => [...text].map((char) => ({ char, primary })));
    const previewImages = [
      '/static/home/assets/images/1.webp',
      '/static/home/assets/images/3.webp',
      '/static/home/assets/images/5.webp',
      '/static/home/assets/images/avatar-AvaReed.webp',
      '/static/home/assets/images/avatar-AlexClient.webp'
    ];

    function renderSlider() {
      if (!shell) return;
      shell.classList.add('microinteraction-code-shell');
      shell.innerHTML = `
        <div class="micro-slider-ui">
          <div class="micro-slider-copy">
            <h4>This is an interactive slider <span class="bg-linear-to-r from-neutral-200 to-transparent">created for you only</span> with motion.</h4>
            <p>We know that thoughtful motion can be expensive, that’s why we build it into the system.</p>
            <div class="micro-slider-control" role="slider" tabindex="0" aria-label="Interactive motion slider" aria-valuemin="0" aria-valuemax="100" aria-valuenow="40">
              <div class="micro-slider-fill"></div>
              <div class="micro-slider-ticks">${'<span></span>'.repeat(9)}</div>
              <div class="micro-slider-preview"><img src="/static/home/assets/images/avatar-AvaReed.webp" alt="Analysis preview"></div>
              <div class="micro-slider-thumb"></div>
            </div>
          </div>
        </div>`;
      const slider = $('.micro-slider-control', shell);
      const fill = $('.micro-slider-fill', slider);
      const thumb = $('.micro-slider-thumb', slider);
      const preview = $('.micro-slider-preview', slider);
      const previewImage = $('img', preview);
      let value = .4;
      let dragging = false;
      let lastValue = value;

      const update = (next) => {
        value = Math.max(0, Math.min(1, next));
        const pct = `${value * 100}%`;
        fill.style.width = pct;
        thumb.style.left = pct;
        preview.style.left = pct;
        preview.style.transform = `translateX(-50%) rotate(${Math.max(-8, Math.min(8, (value - lastValue) * 70))}deg)`;
        previewImage.src = previewImages[Math.min(previewImages.length - 1, Math.floor(value * previewImages.length))];
        slider.setAttribute('aria-valuenow', String(Math.round(value * 100)));
        lastValue = value;
      };
      const fromEvent = (event) => {
        const rect = slider.getBoundingClientRect();
        update((event.clientX - rect.left) / rect.width);
      };
      slider.addEventListener('pointerdown', (event) => {
        dragging = true;
        slider.classList.add('is-dragging');
        slider.setPointerCapture?.(event.pointerId);
        fromEvent(event);
      });
      slider.addEventListener('pointermove', (event) => { if (dragging) fromEvent(event); });
      slider.addEventListener('pointerup', () => { dragging = false; slider.classList.remove('is-dragging'); });
      slider.addEventListener('pointercancel', () => { dragging = false; slider.classList.remove('is-dragging'); });
      slider.addEventListener('keydown', (event) => {
        if (!['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return;
        event.preventDefault();
        if (event.key === 'Home') update(0);
        else if (event.key === 'End') update(1);
        else update(value + (event.key === 'ArrowRight' ? .05 : -.05));
      });
    }

    function typeMicroCode(index = 0) {
      if (!microRunning || !code || !shell) return;
      if (index === 0) {
        shell.classList.add('microinteraction-code-shell');
        shell.innerHTML = '<pre class="font-mono text-[11px] leading-relaxed tracking-tight md:text-xs mask-r-from-90% text-[#24292f]"><code class="font-mono"></code></pre>';
      }
      const target = $('code', shell);
      if (!target) return;
      if (index >= chars.length) {
        const caret = document.createElement('span');
        caret.className = 'ml-px inline-block h-[1.1em] w-0.5 animate-pulse align-[-0.125em] bg-[#0969da]';
        target.appendChild(caret);
        microTimer = window.setTimeout(() => {
          renderSlider();
          microTimer = window.setTimeout(() => typeMicroCode(0), 10000);
        }, 950);
        return;
      }
      const item = chars[index];
      const span = document.createElement('span');
      if (item.primary) span.style.color = '#0550ae';
      span.textContent = item.char;
      target.appendChild(span);
      microTimer = window.setTimeout(() => typeMicroCode(index + 1), 7);
    }

    const observer = new IntersectionObserver(([entry]) => {
      islandRunning = entry.isIntersecting;
      microRunning = entry.isIntersecting;
      clearTimeout(islandTimer);
      clearTimeout(microTimer);
      if (entry.isIntersecting) {
        queueIslandCycle();
        typeMicroCode(0);
      } else {
        islandState('idle');
      }
    }, { threshold: .12 });
    observer.observe(section);
  }

  function setupPricing() {
    const cards = $$('[data-home-pricing-card]');
    if (!cards.length) return;

    const number = new Intl.NumberFormat('en-NP', { maximumFractionDigits: 2 });
    const titleCase = (value) => value
      .split('_')
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
      .join(' ');

    const updateCard = (card, plan) => {
      const resources = plan.resources || {};
      const monthly = Number(plan.price_monthly || 0);
      const annual = Number(plan.price_annual || 0);
      const tiers = (plan.allowed_tiers || []).map(titleCase);
      const features = [
        `${resources.ram_gb || 0} GB RAM and ${resources.vcpu || 0} vCPU`,
        `${resources.storage_gb || 0} GB evidence storage`,
        tiers.length ? `${tiers.join(', ')} module access` : 'Plan-scoped module access',
        plan.allowed_instance_count
          ? `${plan.allowed_instance_count} isolated analysis instance${plan.allowed_instance_count === 1 ? '' : 's'}`
          : 'Plan-scoped analysis capacity',
        annual > 0 ? `Annual billing: Rs. ${number.format(annual)}` : 'No-cost annual access',
      ];

      $('[data-plan-name]', card).textContent = plan.display_name;
      $('[data-plan-description]', card).textContent = plan.description;
      $('[data-plan-price-prefix]', card).textContent = monthly > 0 ? 'Monthly' : 'Plan price';
      $('[data-plan-currency]', card).textContent = monthly > 0 ? 'Rs.' : '';
      $('[data-plan-price]', card).textContent = monthly > 0 ? number.format(monthly) : 'Free';
      $('[data-plan-period]', card).textContent = monthly > 0 ? '/month' : '';

      const list = $('[data-plan-features]', card);
      const icon = $('li svg', list)?.cloneNode(true);
      list.replaceChildren(...features.map((text) => {
        const item = document.createElement('li');
        item.className = 'flex items-center gap-2';
        if (icon) item.appendChild(icon.cloneNode(true));
        item.appendChild(document.createTextNode(text));
        return item;
      }));

      const cta = $('[data-plan-cta]', card);
      cta.setAttribute('aria-label', `Get started with the ${plan.display_name} plan`);
    };

    fetch('/api/plans', { headers: { Accept: 'application/json' } })
      .then((response) => {
        if (!response.ok) throw new Error(`Plan API returned ${response.status}`);
        return response.json();
      })
      .then(({ plans = [] }) => {
        const paidPlans = plans.filter((plan) => Number(plan.price_monthly) > 0);
        const featuredPlans = (paidPlans.length ? paidPlans : plans).slice(0, cards.length);
        featuredPlans.forEach((plan, index) => updateCard(cards[index], plan));
      })
      .catch(() => {
        // Project-aligned fallback values are already rendered in the template.
      });
  }

  function setupWorkShowcase() {
    const stage = $('[data-work-showcase]');
    if (!stage) return;
    const items = [
      { title:'Incident Response Workspace', country:'Case management', image:'https://assets.aceternity.com/templates/productized-agency-5.webp', fallback:'/static/home/assets/images/hero-2.webp', description:'Coordinate case scope, members, evidence, notes, findings, and reporting in one auditable workspace.' },
      { title:'Evidence Integrity', country:'Chain of custody', image:'https://assets.aceternity.com/templates/minimalist-portfolio-template-1.webp', fallback:'/static/home/assets/images/hero-3.webp', description:'Stream resumable uploads to object storage and verify every artifact with SHA-256 and MD5 hashes.' },
      { title:'Containerized Analysis', country:'Isolated forensic tools', image:'https://assets.aceternity.com/templates/simplistic-saas-template-1.webp', fallback:'/static/home/assets/images/feature-section-with-horizontal-skeletons.webp', description:'Run plan-aware analysis jobs in ephemeral light, medium, heavy, or full worker containers.' },
      { title:'Raw Analysis Results', country:'Preserved output', image:'https://assets.aceternity.com/templates/simplistic-saas-template-3.webp', fallback:'/static/home/assets/images/features-with-isometric-blocks.webp', description:'Keep unmodified stdout and stderr beside the evidence, job configuration, and resulting findings.' },
      { title:'Findings & Indicators', country:'Structured investigation data', image:'https://assets.aceternity.com/templates/simplistic-saas-template-2.webp', fallback:'/static/home/assets/images/multi-illustration-bento.webp', description:'Promote verified observations and IOCs into reusable records without losing their source context.' },
      { title:'Timeline Reconstruction', country:'Chronological analysis', image:'https://assets.aceternity.com/templates/template-preview-7.webp', fallback:'/static/home/assets/images/parallax-hero-images-2.webp', description:'Turn case activity and forensic events into a clear, reviewable incident narrative.' },
      { title:'Investigation Reports', country:'Defensible reporting', image:'https://assets.aceternity.com/templates/template-preview-1.webp', fallback:'/static/home/assets/images/shader-1.webp', description:'Build markdown reports from saved findings, indicators, evidence references, and timeline events.' },
      { title:'Organization RBAC', country:'Scoped access control', image:'https://assets.aceternity.com/templates/template-preview-5.webp', fallback:'/static/home/assets/images/keyboard-2.webp', description:'Separate platform roles from organization roles and delegate only the permissions each team needs.' },
      { title:'Extensible Modules', country:'YAML pipelines and testing', image:'https://assets.aceternity.com/templates/schedule-1-min.webp', fallback:'/static/home/assets/images/hero-landscape.webp', description:'Author, route, and sandbox-test custom forensic modules and multi-step tool pipelines.' }
    ];
    const track = $('[data-work-track]', stage);
    const doubled = [...items, ...items];
    track.innerHTML = doubled.map((item) => `<div class="work-marquee-item"><img src="${item.image}" data-fallback="${item.fallback}" alt="" loading="lazy"></div>`).join('');
    $$('img[data-fallback]', track).forEach((img) => img.addEventListener('error', () => { if (img.src.endsWith(img.dataset.fallback)) return; img.src = img.dataset.fallback; }, { once:true }));

    const card = $('[data-work-card]', stage);
    const inner = $('.work-feature-inner', card);
    const image = $('[data-work-active-image]', card);
    const title = $('[data-work-title]', card);
    const country = $('[data-work-country]', card);
    const description = $('[data-work-description]', card);
    let active = 0;
    let paused = false;
    let timer = 0;

    function setActive(index) {
      active = (index + items.length) % items.length;
      const item = items[active];
      image.classList.add('is-switching');
      window.setTimeout(() => {
        image.src = item.image;
        image.dataset.fallback = item.fallback;
        image.alt = item.title;
        title.textContent = item.title;
        country.textContent = item.country;
        description.textContent = item.description;
        requestAnimationFrame(() => image.classList.remove('is-switching'));
      }, 220);
    }
    image.addEventListener('error', () => { image.src = image.dataset.fallback || '/static/home/assets/images/hero-2.webp'; });
    const cycle = () => {
      clearTimeout(timer);
      timer = window.setTimeout(() => {
        if (!paused) setActive(active + 1);
        cycle();
      }, 3000);
    };
    cycle();

    const pause = (value) => { paused = value; };
    card.addEventListener('mouseenter', () => pause(true));
    card.addEventListener('mouseleave', () => { pause(false); inner.style.transform = ''; });
    card.addEventListener('focusin', () => pause(true));
    card.addEventListener('focusout', () => pause(false));
    card.addEventListener('pointermove', (event) => {
      if (reducedMotion) return;
      const rect = card.getBoundingClientRect();
      const nx = (event.clientX - rect.left) / rect.width - .5;
      const ny = (event.clientY - rect.top) / rect.height - .5;
      inner.style.transform = `rotateX(${-ny * 6}deg) rotateY(${nx * 8}deg)`;
    });
  }

  function setupServiceAnimations() {
    const cards = $$('[data-service-card]');
    if (!cards.length) return;

    // Web-design preview: restore the pointer traversal seen in the original card.
    const design = cards[0];
    if (design && !design.querySelector('.service-preview-cursor')) {
      const visual = design.querySelector('.h-80') || design;
      visual.style.position = 'relative';
      const cursor = document.createElement('div');
      cursor.className = 'service-preview-cursor';
      visual.appendChild(cursor);
    }

    // Deployment notification card.
    const deploy = cards[1];
    if (deploy) {
      const toast = [...deploy.querySelectorAll('div')].find((el) => (el.getAttribute('style') || '').includes('opacity:0.92'));
      toast?.classList.add('service-deploy-toast');
    }

    // Copywriting card: prompt becomes answer while hovering.
    const copy = cards[2];
    if (copy) {
      const shell = [...copy.querySelectorAll('div')].find((el) => (el.getAttribute('style') || '').includes('min-height:5rem'));
      const result = copy.querySelector('[role="presentation"]');
      const prompt = result?.previousElementSibling;
      shell?.classList.add('service-copy-shell');
      prompt?.classList.add('service-copy-prompt');
      result?.classList.add('service-copy-result');
    }

    // Consultation card: video-call view expands into the page mockup.
    const consult = cards[3];
    if (consult) {
      const frame = [...consult.querySelectorAll('div')].find((el) => (el.getAttribute('style') || '').includes('width:300px;height:200px'));
      if (frame) {
        frame.classList.add('service-consult-frame');
        const page = [...frame.children].find((el) => (el.getAttribute('style') || '').includes('opacity:0'));
        const video = [...frame.children].find((el) => (el.getAttribute('style') || '').includes('opacity:1') && el.querySelector('img'));
        const controls = [...frame.children].find((el) => (el.className || '').toString().includes('from-black/55'));
        page?.classList.add('service-consult-page');
        video?.classList.add('service-consult-video');
        controls?.classList.add('service-consult-controls');
      }
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    setupSmoothNavigation();
    setupMobileMenu();
    setupReveals();
    setupCopyAndChat();
    setupHeroCanvas();
    setupProcessAnimations();
    setupPricing();
    setupWorkShowcase();
    setupServiceAnimations();
  });
})();
