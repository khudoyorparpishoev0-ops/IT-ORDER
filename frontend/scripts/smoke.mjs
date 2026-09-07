/**
 * Дымовой прогон панели: открывает все разделы в обеих темах и обоих
 * вариантах шелла, снимает скриншоты и падает при ошибке в консоли
 * или ответе >= 400.
 *
 * Запуск:  npm run build && npm run preview &   (порт 4173)
 *          npm run smoke
 * Путь к Chromium — PW_CHROMIUM, иначе берётся браузер Playwright.
 */
import { chromium } from 'playwright';
import { mkdir } from 'node:fs/promises';

const BASE = process.env.SMOKE_BASE ?? 'http://127.0.0.1:4173';
const OUT = process.env.SHOT_DIR ?? './.shots';
const EXECUTABLE = process.env.PW_CHROMIUM;

const ALL = [
  ['/', 'dashboard'],
  ['/requests', 'requests'],
  ['/approvals', 'approvals'],
  ['/reports', 'reports'],
  ['/team', 'team'],
  ['/finance', 'finance'],
  ['/settings', 'settings'],
  ['/help', 'help'],
  ['/system', 'system'],
];

await mkdir(OUT, { recursive: true });
const browser = await chromium.launch(EXECUTABLE ? { executablePath: EXECUTABLE } : {});
const problems = [];

async function run(label, theme, variant, routes) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  await ctx.addInitScript(
    ([t, v]) => {
      localStorage.setItem('hona-core:theme', t);
      localStorage.setItem('hona-core:variant', v);
    },
    [theme, variant],
  );
  const page = await ctx.newPage();
  page.on('pageerror', (e) => problems.push(`[${label}] pageerror ${e.message}`));
  page.on('requestfailed', (r) => problems.push(`[${label}] failed ${r.url()}`));
  page.on('response', (r) => {
    if (r.status() >= 400) problems.push(`[${label}] ${r.status()} ${r.url()}`);
  });

  for (const [route, name] of routes) {
    await page.goto(BASE + route, { waitUntil: 'networkidle' });
    await page.screenshot({ path: `${OUT}/${label}-${name}.png`, fullPage: true });
    const h1 = await page.locator('h1').first().textContent();
    console.log(`${label} ${route} → ${h1}`);
  }
  await ctx.close();
}

await run('B-light', 'light', 'dispatch', ALL);
await run('B-dark', 'dark', 'dispatch', ALL);
await run('C-light', 'light', 'light', ALL);
await browser.close();

if (problems.length) {
  console.error('ПРОБЛЕМЫ:\n' + [...new Set(problems)].join('\n'));
  process.exit(1);
}
console.log('Дымовой прогон пройден: ошибок нет');
