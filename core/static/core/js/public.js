(() => {
const $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
const RM = matchMedia('(prefers-reduced-motion:reduce)').matches;
const body = document.body;

const secretLogin = $('#secret-login');
const brandLink = $('.bar .logo');
if (secretLogin && brandLink) {
  let clickCount = 0;
  document.addEventListener('pointerdown', e => {
    if (!brandLink.contains(e.target)) clickCount = 0;
  }, true);
  brandLink.addEventListener('click', e => {
    if (e.detail === 0) return;
    e.preventDefault();
    clickCount += 1;
    if (clickCount >= 3) window.location.assign(secretLogin.href);
  });
}

function toast(m) {
  const e = $('#toast'); if (!e || !m) return;
  e.textContent = m; e.classList.add('show');
  clearTimeout(toast.t); toast.t = setTimeout(() => e.classList.remove('show'), 2600);
}
window.siteToast = toast;
const flash = $('#toast')?.dataset.flash; if (flash) toast(flash);

// mobile menu
document.addEventListener('click', e => {
  const menuButton = e.target.closest('#mb');
  if (menuButton) {
    const open = !body.classList.contains('nav');
    body.classList.toggle('nav', open);
    menuButton.setAttribute('aria-expanded', String(open));
    return;
  }
  if (e.target.closest('#nv a') || !e.target.closest('#nv')) {
    body.classList.remove('nav');
    $('#mb')?.setAttribute('aria-expanded', 'false');
  }
});

// social cluster
const socs = $('#socs');
function socToggle(open) {
  if (!socs) return;
  const o = open === undefined ? !socs.classList.contains('open') : open;
  socs.classList.toggle('open', o);
  $('.sbt', socs).setAttribute('aria-expanded', o);
  $$('.sb:not(.sbt)', socs).forEach(a => a.tabIndex = o && !a.hasAttribute('data-social-empty') ? 0 : -1);
}
document.addEventListener('click', e => {
  if (e.target.closest('[data-socs]')) { socToggle(); return; }
  if (socs && !e.target.closest('#socs')) socToggle(false);
});
addEventListener('keydown', e => { if (e.key === 'Escape') socToggle(false); });
let ly = 0;
addEventListener('scroll', () => {
  const y = scrollY;
  document.documentElement.style.setProperty('--sy', y);
  if (y < ly - 2) socToggle(false);
  ly = y;
}, { passive: true });

// scroll-down arrow
document.addEventListener('click', e => {
  const a = e.target.closest('[data-scroll]'); if (!a) return;
  e.preventDefault();
  const sec = a.closest('section'), nx = sec && (sec.nextElementSibling?.nextElementSibling || sec.nextElementSibling);
  if (nx) nx.scrollIntoView({ behavior: RM ? 'auto' : 'smooth' });
});

// product thumbnails
document.addEventListener('click', e => {
  const b = e.target.closest('[data-thumb]'); if (!b) return;
  let img = $('#mainpic');
  if (!img) { img = document.createElement('img'); img.id = 'mainpic'; img.alt = ''; $('.art.big')?.appendChild(img); }
  img.src = b.dataset.thumb;
  img.style.cssText = '';
});

// focus + rail (home sections)
function applyCrop(img, pos) {
  const [p, z] = (pos || '').split('|');
  if (/^\d{1,3}% \d{1,3}%$/.test(p || '')) { img.style.objectPosition = p; img.style.transformOrigin = p; img.style.setProperty('--z', z || 1); }
  else { img.style.objectPosition = ''; img.style.transformOrigin = ''; img.style.removeProperty('--z'); }
}
document.addEventListener('click', e => {
  const rb = e.target.closest('[data-rail]');
  if (rb) { const r = rb.parentElement.querySelector('[data-rail-list]'); r.scrollBy({ left: +rb.dataset.rail * r.clientWidth * .7, behavior: 'smooth' }); return; }
  const b = e.target.closest('[data-focus-btn]'); if (!b) return;
  const root = b.closest('section')?.querySelector('[data-focus]'); if (!root) return;
  const go = () => {
    $$('.rc', b.parentElement).forEach(x => x.classList.toggle('cur', x === b));
    const art = $('[data-f-art]', root); art.style.cssText = 'background:' + b.dataset.art.replace(/^background:/, '');
    art.innerHTML = '';
    if (b.dataset.img) { const im = document.createElement('img'); im.src = b.dataset.img; im.alt = ''; applyCrop(im, b.dataset.pos); art.appendChild(im); }
    $('[data-f-small]', root).textContent = b.dataset.small;
    $('[data-f-title]', root).textContent = b.dataset.title;
    $('[data-f-sub]', root).textContent = b.dataset.sub;
    $('[data-f-link]', root).href = b.dataset.href;
  };
  document.startViewTransition && !RM ? document.startViewTransition(go) : go();
});
$$('[data-rail-list]').forEach(r => {
  const u = () => {
    const b = r.getBoundingClientRect(), c = b.left + b.width / 2;
    $$('.rc', r).forEach(k => {
      const q = k.getBoundingClientRect(), d = Math.max(-1, Math.min(1, (q.left + q.width / 2 - c) / (b.width / 2)));
      k.style.setProperty('--d', Math.abs(d).toFixed(3)); k.style.setProperty('--s', d < 0 ? -1 : 1);
    });
  };
  r.addEventListener('scroll', () => requestAnimationFrame(u), { passive: true }); u();
});

// reveal on scroll
const reveal = $$('.sec-h,a.card,.focus,.railw,.two>*,.facts li');
if (body.classList.contains('edit') || RM) reveal.forEach(e => e.classList.add('in', 'na'));
else if ('IntersectionObserver' in window) {
  const io = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); } }), { threshold: .1 });
  reveal.forEach((e, i) => { e.style.setProperty('--d', (i % 6) * 80 + 'ms'); io.observe(e); });
} else reveal.forEach(e => e.classList.add('in', 'na'));

// pointer effects
document.addEventListener('pointermove', e => {
  if (RM || e.pointerType === 'touch' || !e.target.closest) return;
  const s = e.target.closest('.stage');
  if (s) {
    const b = s.getBoundingClientRect();
    s.style.setProperty('--mx', ((e.clientX - b.left) / b.width * 2 - 1).toFixed(3));
    s.style.setProperty('--my', ((e.clientY - b.top) / b.height * 2 - 1).toFixed(3));
    s.style.setProperty('--px', e.clientX - b.left + 'px'); s.style.setProperty('--py', e.clientY - b.top + 'px');
  }
  const c = e.target.closest('a.card,.rc');
  if (c) {
    const b = c.getBoundingClientRect(), x = (e.clientX - b.left) / b.width, y = (e.clientY - b.top) / b.height;
    c.style.setProperty('--rx', ((.5 - y) * 10).toFixed(2) + 'deg'); c.style.setProperty('--ry', ((x - .5) * 12).toFixed(2) + 'deg');
    c.style.setProperty('--gx', x * 100 + '%'); c.style.setProperty('--gy', y * 100 + '%');
  }
});
document.addEventListener('pointerout', e => {
  const c = e.target.closest && e.target.closest('a.card,.rc');
  if (c && !c.contains(e.relatedTarget)) ['--rx', '--ry'].forEach(q => c.style.removeProperty(q));
});
})();
