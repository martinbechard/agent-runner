document.querySelectorAll('[data-copy]').forEach((button) => button.addEventListener('click', async () => {
  const target = document.querySelector(button.getAttribute('data-copy'));
  if (!target) return;
  await navigator.clipboard?.writeText(target.textContent ?? '');
  button.textContent = 'Copied';
  window.setTimeout(() => { button.textContent = 'Copy'; }, 1200);
}));
