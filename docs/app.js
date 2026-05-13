// Landing page — minimal progressive enhancement.
// Smooth-scroll for hash links, and reveal-on-scroll for cards.

document.querySelectorAll('a[href^="#"]').forEach(a => {
  a.addEventListener('click', e => {
    const id = a.getAttribute('href').slice(1);
    if (!id) return;
    const el = document.getElementById(id);
    if (!el) return;
    e.preventDefault();
    el.scrollIntoView({behavior: 'smooth', block: 'start'});
    history.replaceState(null, '', '#' + id);
  });
});

// Reveal-on-scroll (progressive; if IntersectionObserver is missing, nothing breaks)
if ('IntersectionObserver' in window) {
  const io = new IntersectionObserver(entries => {
    entries.forEach(e => {
      if (e.isIntersecting) {
        e.target.classList.add('in');
        io.unobserve(e.target);
      }
    });
  }, {rootMargin: '0px 0px -10% 0px', threshold: 0.12});

  document.querySelectorAll('.section, .card, .sol-row, .screen').forEach(el => io.observe(el));
}

// Ambient parallax on hero glow (desktop only)
const hero = document.querySelector('.hero');
if (hero && matchMedia('(hover:hover)').matches) {
  hero.addEventListener('mousemove', e => {
    const r = hero.getBoundingClientRect();
    const x = ((e.clientX - r.left) / r.width - 0.5) * 20;
    const y = ((e.clientY - r.top) / r.height - 0.5) * 20;
    hero.style.setProperty('--mx', x + 'px');
    hero.style.setProperty('--my', y + 'px');
  });
}
