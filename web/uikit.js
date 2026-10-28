// Preferences shared by the pages (text size, spoken messages) and the one sentence that tells the person what to do next.
const KEY = 'medtable.bigtext';
let lastSpoken = '';

export function initPrefs() {
  const apply = big => {
    document.documentElement.classList.toggle('big', big);
    try { localStorage.setItem(KEY, big ? '1' : '0'); } catch { /* private mode: the choice is just not remembered */ }
    document.getElementById('textBigger')?.setAttribute('aria-pressed', big);
    document.getElementById('textSmaller')?.setAttribute('aria-pressed', !big);
  };
  let stored = false;
  try { stored = localStorage.getItem(KEY) === '1'; } catch { /* ignore */ }
  apply(stored);
  document.getElementById('textBigger')?.addEventListener('click', () => apply(true));
  document.getElementById('textSmaller')?.addEventListener('click', () => apply(false));
}

// Spoken with the voice of the device (nothing is downloaded or sent). Only when the person ticked "Read messages aloud", and never the same sentence twice in a row.
export function say(text) {
  if (!document.getElementById('voice')?.checked || !('speechSynthesis' in window) || !text || text === lastSpoken) return;
  lastSpoken = text;
  speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = 'en-US'; utterance.rate = 0.9;
  speechSynthesis.speak(utterance);
}
export function forgetSpoken() { lastSpoken = ''; }

// One sentence, with a level ("good", "mid", "bad", or "" for neutral): shown in the #advice banner, announced to screen readers (role="status") and, if asked, spoken.
export function showAdvice(text, level = '', speak = true) {
  const banner = document.getElementById('advice');
  if (!banner) return;
  if (banner.textContent !== text) banner.textContent = text;
  banner.className = level;
  if (speak) say(text);
}
