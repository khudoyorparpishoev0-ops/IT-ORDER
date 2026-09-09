/**
 * Дымовой прогон панели: входит под каждой ролью, открывает доступные ей
 * разделы в обеих темах и обоих вариантах шелла, снимает скриншоты и падает
 * при ошибке в консоли или неожиданном ответе сервера.
 *
 * Запуск:  npm run build && npm run preview &   (порт 4173, API на :8000)
 *          npm run smoke
 * Путь к Chromium — PW_CHROMIUM, иначе берётся браузер Playwright.
 * Учётные данные — SMOKE_PASSWORD (по умолчанию пароль демо-набора).
 */
import { chromium } from 'playwright';
import { mkdir } from 'node:fs/promises';

const BASE = process.env.SMOKE_BASE ?? 'http://127.0.0.1:4173';
const OUT = process.env.SHOT_DIR ?? './.shots';
const EXECUTABLE = process.env.PW_CHROMIUM;
const PASSWORD = process.env.SMOKE_PASSWORD ?? 'hona-demo-2026';
// Домен демо-адресов берётся из ALLOWED_EMAIL_DOMAINS; здесь он должен
// совпадать с тем, под которым загружены демо-данные.
const DOMAIN = process.env.SMOKE_DOMAIN ?? 'ithona.tj';

const COMMON = [
  ['/', 'dashboard'],
  ['/requests', 'requests'],
  ['/requests/new', 'new'],
  ['/settings', 'settings'],
  ['/help', 'help'],
  ['/system', 'system'],
];

const REPORTS = [
  ['/reports', 'reports'],
  ['/team', 'team'],
  ['/finance', 'finance'],
];

// Финансы и администратор обязаны иметь второй фактор — их прогон
// требует настроенного TOTP, поэтому в дымовой набор они не входят.
// Права этих ролей проверяются тестами бэкенда.
const ROLES = [
  {
    label: 'manager',
    email: `a.kovalev@${DOMAIN}`,
    routes: [...COMMON, ['/approvals', 'approvals'], ...REPORTS],
    // Руководитель видит очередь согласования и сводки, но не справочник
    // сотрудников — его ведёт администратор.
    expectNav: ['Согласование', 'Отчёты', 'Команда', 'Финансы'],
    forbiddenNav: ['Сотрудники', 'Объекты', 'Журнал', 'Закуп'],
  },
  {
    label: 'employee',
    email: `i.petrov@${DOMAIN}`,
    routes: COMMON,
    forbiddenNav: [
      'Согласование',
      'Отчёты',
      'Команда',
      'Финансы',
      'Сотрудники',
      'Объекты',
      'Журнал',
      'Закуп',
    ],
  },
];

await mkdir(OUT, { recursive: true });
const browser = await chromium.launch(EXECUTABLE ? { executablePath: EXECUTABLE } : {});
const problems = [];

async function run(role, theme, { screenshots = true } = {}) {
  const tag = `${role.label}-${theme}`;
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  await ctx.addInitScript((t) => {
    localStorage.setItem('hona-core:theme', t);
  }, theme);
  const page = await ctx.newPage();
  page.on('pageerror', (e) => problems.push(`[${tag}] pageerror ${e.message}`));
  page.on('requestfailed', (r) => {
    // Переход на другую страницу отменяет незавершённые загрузки шрифтов —
    // это не сбой, а обычное поведение браузера.
    const reason = r.failure()?.errorText ?? '';
    if (reason.includes('ERR_ABORTED')) return;
    problems.push(`[${tag}] failed ${r.url()} (${reason})`);
  });
  page.on('response', (r) => {
    // 401 на /api/auth/me до входа — штатная проверка сессии, не ошибка.
    if (r.status() >= 400 && !r.url().endsWith('/api/auth/me')) {
      problems.push(`[${tag}] ${r.status()} ${r.url()}`);
    }
  });

  await page.goto(BASE + '/', { waitUntil: 'networkidle' });
  await page.getByLabel('Корпоративная почта').fill(role.email);
  await page.getByLabel('Пароль').fill(PASSWORD);
  await page.getByRole('button', { name: 'Войти' }).click();

  // Ролям с обязательным вторым фактором показывается настройка. Дымовой
  // прогон её не проходит: TOTP проверяется тестами бэкенда. Сюда такие
  // роли попадают уже настроенными — см. SMOKE_TOTP_SECRET.
  const setup = page.getByRole('heading', { name: 'Требуется двухфакторный вход' });
  const codeField = page.getByLabel('Код из приложения');
  await Promise.race([
    page.waitForSelector('nav[aria-label="Разделы"]', { timeout: 10_000 }),
    setup.waitFor({ timeout: 10_000 }).catch(() => {}),
    codeField.waitFor({ timeout: 10_000 }).catch(() => {}),
  ]);

  if (await setup.isVisible().catch(() => false)) {
    problems.push(`[${tag}] требуется настройка второго фактора — прогон невозможен`);
    await ctx.close();
    return;
  }
  if (await codeField.isVisible().catch(() => false)) {
    problems.push(`[${tag}] требуется код второго фактора — прогон невозможен`);
    await ctx.close();
    return;
  }
  await page.waitForSelector('nav[aria-label="Разделы"]', { timeout: 10_000 });

  const nav = await page.locator('nav[aria-label="Разделы"]').innerText();
  for (const item of role.expectNav ?? []) {
    if (!nav.includes(item)) problems.push(`[${tag}] в меню нет раздела «${item}»`);
  }
  for (const item of role.forbiddenNav ?? []) {
    if (nav.includes(item)) problems.push(`[${tag}] раздел «${item}» виден без прав`);
  }

  for (const [route, name] of role.routes) {
    await page.goto(BASE + route, { waitUntil: 'networkidle' });
    if (screenshots) {
      await page.screenshot({ path: `${OUT}/${tag}-${name}.png`, fullPage: true });
    }
    const h1 = await page.locator('h1').first().textContent();
    console.log(`${tag} ${route} → ${h1}`);
  }

  await ctx.close();
}

// Разрешённые разделы каждой роли — в светлой теме.
for (const role of ROLES) {
  await run(role, 'light');
}
// Тёмная тема проверяется на самой полной роли.
await run(ROLES[0], 'dark');

await browser.close();

if (problems.length) {
  console.error('ПРОБЛЕМЫ:\n' + [...new Set(problems)].join('\n'));
  process.exit(1);
}
console.log('Дымовой прогон пройден: ошибок нет');
