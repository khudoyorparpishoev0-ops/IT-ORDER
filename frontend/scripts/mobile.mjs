/**
 * Проверка панели на телефоне: ни одна страница не должна прокручиваться
 * вбок. Горизонтальная прокрутка страницы — не косметика: с ней половина
 * таблицы уезжает за край, и человек её просто не находит.
 *
 * Запуск:  npm run build && npm run preview &   (порт 4173, API на :8000)
 *          npm run mobile
 * Путь к Chromium — PW_CHROMIUM, учётные данные — SMOKE_PASSWORD.
 *
 * Скриншоты складываются в .shots/mobile — по ним видно, что получилось,
 * а не только что ничего не сломалось.
 */
import { chromium, devices } from 'playwright';
import { mkdir } from 'node:fs/promises';

const BASE = process.env.SMOKE_BASE ?? 'http://127.0.0.1:4173';
const OUT = process.env.SHOT_DIR ?? './.shots/mobile';
const EXECUTABLE = process.env.PW_CHROMIUM;
const PASSWORD = process.env.SMOKE_PASSWORD ?? 'hona-demo-2026';
const DOMAIN = process.env.SMOKE_DOMAIN ?? 'ithona.tj';

const ROLES = [
  {
    label: 'manager',
    email: `a.kovalev@${DOMAIN}`,
    routes: ['/', '/requests', '/approvals', '/stock', '/reports', '/team', '/finance', '/settings'],
  },
  {
    label: 'employee',
    email: `i.petrov@${DOMAIN}`,
    routes: ['/', '/requests', '/settings'],
  },
];

const problems = [];

/** Ширина документа против ширины экрана. Разница — и есть уехавшая вбок вёрстка. */
async function checkWidth(page, where) {
  const { vw, scroll, wide } = await page.evaluate(() => {
    const vw = document.documentElement.clientWidth;
    const wide = [];
    for (const el of document.querySelectorAll('*')) {
      const r = el.getBoundingClientRect();
      if (r.right > vw + 1)
        wide.push(`${el.tagName.toLowerCase()}.${String(el.className).slice(0, 30)}`);
    }
    return { vw, scroll: document.documentElement.scrollWidth, wide: wide.slice(0, 3) };
  });
  const ok = scroll <= vw + 1;
  console.log(`${ok ? 'ok  ' : 'ШИРЕ'} ${where} — экран ${vw}, документ ${scroll}`);
  if (!ok) problems.push(`${where}: документ ${scroll} при экране ${vw} (${wide.join(', ')})`);
}

await mkdir(OUT, { recursive: true });
const browser = await chromium.launch(EXECUTABLE ? { executablePath: EXECUTABLE } : {});
const context = await browser.newContext({ ...devices['iPhone 13'] });
const page = await context.newPage();
page.on('pageerror', (e) => problems.push(`ошибка страницы: ${e.message}`));

await page.goto(`${BASE}/login`);
await page.waitForTimeout(600);
await checkWidth(page, '/login');
await page.screenshot({ path: `${OUT}/login.png` });

for (const role of ROLES) {
  // Со старой сессией /login сразу уводит в панель, и следующая роль
  // входит под предыдущей.
  await context.clearCookies();
  await page.goto(`${BASE}/login`);
  await page.waitForTimeout(400);
  await page.fill('input[type=email]', role.email);
  await page.fill('input[type=password]', PASSWORD);
  await page.click('button[type=submit]');
  await page.waitForTimeout(2000);

  for (const route of role.routes) {
    await page.goto(BASE + route);
    await page.waitForTimeout(1000);
    await checkWidth(page, `${role.label} ${route}`);
    await page.screenshot({ path: `${OUT}/${role.label}${route.replace(/\//g, '-')}.png` });
  }

  if (role.label === 'manager') {
    // Шторка меню и оба окна: именно в них вёрстка ломается тише всего.
    await page.goto(`${BASE}/`);
    await page.waitForTimeout(800);
    await page.getByRole('button', { name: 'Меню разделов' }).click();
    await page.waitForTimeout(500);
    await checkWidth(page, 'меню');
    await page.screenshot({ path: `${OUT}/menu.png` });
    await page.keyboard.press('Escape');

    // Нижняя панель: есть на разделах, «Ещё» открывает шторку, на форме
    // заявки панели нет.
    await page.goto(`${BASE}/`);
    await page.waitForTimeout(800);
    if (!(await page.locator('nav.tabbar').isVisible())) problems.push('нижняя панель не показана на дашборде');
    await page.getByRole('button', { name: 'Ещё разделы' }).click();
    await page.waitForTimeout(500);
    if (!(await page.locator('.sidebar .nav-item').first().isVisible())) problems.push('«Ещё» не открывает шторку');
    await checkWidth(page, 'шторка по «Ещё»');
    await page.keyboard.press('Escape');

    await page.goto(`${BASE}/requests/new`);
    await page.waitForTimeout(1000);
    await checkWidth(page, 'форма «Новая заявка»');
    if (await page.locator('nav.tabbar').isVisible()) problems.push('нижняя панель показана на форме заявки');
    await page.screenshot({ path: `${OUT}/form-new.png` });

    await page.goto(`${BASE}/requests`);
    await page.waitForTimeout(1000);
    await page.locator('table.tbl tbody tr').first().click();
    await page.waitForTimeout(1000);
    await checkWidth(page, 'карточка заявки');
    await page.screenshot({ path: `${OUT}/request.png`, fullPage: true });
  }

  await page.goto(`${BASE}/`);
  await page.waitForTimeout(400);
}

await browser.close();

if (problems.length) {
  console.error('\nНа телефоне съезжает вёрстка:');
  for (const p of problems) console.error(`  ${p}`);
  process.exit(1);
}
console.log('\nМобильная проверка пройдена: страницы вбок не прокручиваются');
