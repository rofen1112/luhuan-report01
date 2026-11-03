(() => {
  const progress = document.querySelector('.reading-progress');
  const tocLinks = Array.from(document.querySelectorAll('.toc a'));
  const sections = tocLinks
    .map((link) => document.querySelector(link.getAttribute('href')))
    .filter(Boolean);

  const updateProgress = () => {
    const scrollable = document.documentElement.scrollHeight - window.innerHeight;
    const ratio = scrollable > 0 ? window.scrollY / scrollable : 0;
    progress.style.width = `${Math.min(100, Math.max(0, ratio * 100))}%`;
  };

  const activateSection = () => {
    const marker = window.scrollY + 150;
    let current = sections[0];
    sections.forEach((section) => {
      if (section.offsetTop <= marker) current = section;
    });
    tocLinks.forEach((link) => {
      link.classList.toggle('active', current && link.getAttribute('href') === `#${current.id}`);
    });
  };

  const onScroll = () => {
    updateProgress();
    activateSection();
  };

  window.addEventListener('scroll', onScroll, { passive: true });
  window.addEventListener('resize', onScroll, { passive: true });
  onScroll();

  document.querySelector('#print-report')?.addEventListener('click', () => window.print());

  document.querySelector('#copy-summary')?.addEventListener('click', async (event) => {
    const button = event.currentTarget;
    const target = document.querySelector('#copy-target');
    if (!target) return;
    try {
      await navigator.clipboard.writeText(target.textContent.trim());
      const original = button.textContent;
      button.textContent = '已复制';
      window.setTimeout(() => { button.textContent = original; }, 1500);
    } catch {
      button.textContent = '请手动复制';
    }
  });
})();
