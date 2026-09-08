import type { CSSProperties } from 'react';

/**
 * Иконки — контурный спрайт по правилам брендбука:
 * stroke-width 1.6 при 24 px, butt/miter, fill none, цвет через currentColor.
 * Геометрия из Tabler Icons (MIT). Цветные иконки и эмодзи запрещены.
 * Финальный комплект услуг рисуется в векторе и заменит этот спрайт.
 */
export type IconName =
  | 'ti-layout-dashboard'
  | 'ti-file-text'
  | 'ti-circle-check'
  | 'ti-circle-x'
  | 'ti-chart-bar'
  | 'ti-users'
  | 'ti-user-plus'
  | 'ti-building'
  | 'ti-package'
  | 'ti-wallet'
  | 'ti-settings'
  | 'ti-help-circle'
  | 'ti-download'
  | 'ti-plus'
  | 'ti-search'
  | 'ti-arrows-sort'
  | 'ti-x'
  | 'ti-sun'
  | 'ti-moon'
  | 'ti-chevron-left'
  | 'ti-chevron-right'
  | 'ti-chevron-down'
  | 'ti-check'
  | 'ti-menu-2'
  | 'ti-file-spreadsheet'
  | 'ti-file-type-pdf'
  | 'ti-clock-hour-4'
  | 'ti-history'
  | 'ti-filter'
  | 'ti-server-2'
  | 'ti-device-cctv';

/** Монтируется один раз в корне приложения. */
export function IconSprite() {
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      style={{ position: 'absolute', width: 0, height: 0, overflow: 'hidden' }}
    >
      <symbol id="ti-layout-dashboard" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="butt" strokeLinejoin="miter">
      <path d="M5 4h4a1 1 0 0 1 1 1v6a1 1 0 0 1 -1 1h-4a1 1 0 0 1 -1 -1v-6a1 1 0 0 1 1 -1"></path>
      <path d="M5 16h4a1 1 0 0 1 1 1v2a1 1 0 0 1 -1 1h-4a1 1 0 0 1 -1 -1v-2a1 1 0 0 1 1 -1"></path>
      <path d="M15 12h4a1 1 0 0 1 1 1v6a1 1 0 0 1 -1 1h-4a1 1 0 0 1 -1 -1v-6a1 1 0 0 1 1 -1"></path>
      <path d="M15 4h4a1 1 0 0 1 1 1v2a1 1 0 0 1 -1 1h-4a1 1 0 0 1 -1 -1v-2a1 1 0 0 1 1 -1"></path>
      </symbol>
      <symbol id="ti-file-text" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="butt" strokeLinejoin="miter">
      <path d="M14 3v4a1 1 0 0 0 1 1h4"></path>
      <path d="M17 21h-10a2 2 0 0 1 -2 -2v-14a2 2 0 0 1 2 -2h7l5 5v11a2 2 0 0 1 -2 2"></path>
      <path d="M9 9l1 0"></path>
      <path d="M9 13l6 0"></path>
      <path d="M9 17l6 0"></path>
      </symbol>
      <symbol id="ti-circle-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="butt" strokeLinejoin="miter">
      <path d="M3 12a9 9 0 1 0 18 0a9 9 0 1 0 -18 0"></path>
      <path d="M9 12l2 2l4 -4"></path>
      </symbol>
      <symbol id="ti-circle-x" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="butt" strokeLinejoin="miter">
      <path d="M3 12a9 9 0 1 0 18 0a9 9 0 1 0 -18 0"></path>
      <path d="M10 10l4 4m0 -4l-4 4"></path>
      </symbol>
      <symbol id="ti-chart-bar" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="butt" strokeLinejoin="miter">
      <path d="M3 13a1 1 0 0 1 1 -1h4a1 1 0 0 1 1 1v6a1 1 0 0 1 -1 1h-4a1 1 0 0 1 -1 -1l0 -6"></path>
      <path d="M15 9a1 1 0 0 1 1 -1h4a1 1 0 0 1 1 1v10a1 1 0 0 1 -1 1h-4a1 1 0 0 1 -1 -1l0 -10"></path>
      <path d="M9 5a1 1 0 0 1 1 -1h4a1 1 0 0 1 1 1v14a1 1 0 0 1 -1 1h-4a1 1 0 0 1 -1 -1l0 -14"></path>
      <path d="M4 20h14"></path>
      </symbol>
      <symbol id="ti-users" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="butt" strokeLinejoin="miter">
      <path d="M5 7a4 4 0 1 0 8 0a4 4 0 1 0 -8 0"></path>
      <path d="M3 21v-2a4 4 0 0 1 4 -4h4a4 4 0 0 1 4 4v2"></path>
      <path d="M16 3.13a4 4 0 0 1 0 7.75"></path>
      <path d="M21 21v-2a4 4 0 0 0 -3 -3.85"></path>
      </symbol>
      <symbol id="ti-user-plus" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="butt" strokeLinejoin="miter">
      <path d="M8 7a4 4 0 1 0 8 0a4 4 0 1 0 -8 0"></path>
      <path d="M16 19h6"></path>
      <path d="M19 16v6"></path>
      <path d="M6 21v-2a4 4 0 0 1 4 -4h4"></path>
      </symbol>
      <symbol id="ti-building" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="butt" strokeLinejoin="miter">
      <path d="M3 21h18"></path>
      <path d="M5 21v-16a2 2 0 0 1 2 -2h6a2 2 0 0 1 2 2v16"></path>
      <path d="M15 8h2a2 2 0 0 1 2 2v11"></path>
      <path d="M9 7h1"></path>
      <path d="M9 11h1"></path>
      <path d="M9 15h1"></path>
      </symbol>
      <symbol id="ti-package" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="butt" strokeLinejoin="miter">
      <path d="M12 3l8 4.5v9l-8 4.5l-8 -4.5v-9z"></path>
      <path d="M12 12l8 -4.5"></path>
      <path d="M12 12v9"></path>
      <path d="M12 12l-8 -4.5"></path>
      <path d="M16 5.25l-8 4.5"></path>
      </symbol>
      <symbol id="ti-wallet" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="butt" strokeLinejoin="miter">
      <path d="M17 8v-3a1 1 0 0 0 -1 -1h-10a2 2 0 0 0 0 4h12a1 1 0 0 1 1 1v3m0 4v3a1 1 0 0 1 -1 1h-12a2 2 0 0 1 -2 -2v-12"></path>
      <path d="M20 12v4h-4a2 2 0 0 1 0 -4h4"></path>
      </symbol>
      <symbol id="ti-settings" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="butt" strokeLinejoin="miter">
      <path d="M10.325 4.317c.426 -1.756 2.924 -1.756 3.35 0a1.724 1.724 0 0 0 2.573 1.066c1.543 -.94 3.31 .826 2.37 2.37a1.724 1.724 0 0 0 1.065 2.572c1.756 .426 1.756 2.924 0 3.35a1.724 1.724 0 0 0 -1.066 2.573c.94 1.543 -.826 3.31 -2.37 2.37a1.724 1.724 0 0 0 -2.572 1.065c-.426 1.756 -2.924 1.756 -3.35 0a1.724 1.724 0 0 0 -2.573 -1.066c-1.543 .94 -3.31 -.826 -2.37 -2.37a1.724 1.724 0 0 0 -1.065 -2.572c-1.756 -.426 -1.756 -2.924 0 -3.35a1.724 1.724 0 0 0 1.066 -2.573c-.94 -1.543 .826 -3.31 2.37 -2.37c1 .608 2.296 .07 2.572 -1.065"></path>
      <path d="M9 12a3 3 0 1 0 6 0a3 3 0 0 0 -6 0"></path>
      </symbol>
      <symbol id="ti-help-circle" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="butt" strokeLinejoin="miter">
      <path d="M3 12a9 9 0 1 0 18 0a9 9 0 0 0 -18 0"></path>
      <path d="M12 16v.01"></path>
      <path d="M12 13a2 2 0 0 0 .914 -3.782a1.98 1.98 0 0 0 -2.414 .483"></path>
      </symbol>
      <symbol id="ti-download" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="butt" strokeLinejoin="miter">
      <path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2 -2v-2"></path>
      <path d="M7 11l5 5l5 -5"></path>
      <path d="M12 4l0 12"></path>
      </symbol>
      <symbol id="ti-plus" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="butt" strokeLinejoin="miter">
      <path d="M12 5l0 14"></path>
      <path d="M5 12l14 0"></path>
      </symbol>
      <symbol id="ti-search" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="butt" strokeLinejoin="miter">
      <path d="M3 10a7 7 0 1 0 14 0a7 7 0 1 0 -14 0"></path>
      <path d="M21 21l-6 -6"></path>
      </symbol>
      <symbol id="ti-arrows-sort" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="butt" strokeLinejoin="miter">
      <path d="M3 9l4 -4l4 4m-4 -4v14"></path>
      <path d="M21 15l-4 4l-4 -4m4 4v-14"></path>
      </symbol>
      <symbol id="ti-x" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="butt" strokeLinejoin="miter">
      <path d="M18 6l-12 12"></path>
      <path d="M6 6l12 12"></path>
      </symbol>
      <symbol id="ti-sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="butt" strokeLinejoin="miter">
      <path d="M8 12a4 4 0 1 0 8 0a4 4 0 1 0 -8 0"></path>
      <path d="M3 12h1m8 -9v1m8 8h1m-9 8v1m-6.4 -15.4l.7 .7m12.1 -.7l-.7 .7m0 11.4l.7 .7m-12.1 -.7l-.7 .7"></path>
      </symbol>
      <symbol id="ti-moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="butt" strokeLinejoin="miter">
      <path d="M12 3c.132 0 .263 0 .393 0a7.5 7.5 0 0 0 7.92 12.446a9 9 0 1 1 -8.313 -12.454l0 .008"></path>
      </symbol>
      <symbol id="ti-chevron-left" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="butt" strokeLinejoin="miter"><path d="M15 6l-6 6l6 6"></path></symbol>
      <symbol id="ti-chevron-right" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="butt" strokeLinejoin="miter"><path d="M9 6l6 6l-6 6"></path></symbol>
      <symbol id="ti-chevron-down" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="butt" strokeLinejoin="miter"><path d="M6 9l6 6l6 -6"></path></symbol>
      <symbol id="ti-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="butt" strokeLinejoin="miter"><path d="M5 12l5 5l10 -10"></path></symbol>
      <symbol id="ti-menu-2" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="butt" strokeLinejoin="miter">
      <path d="M4 6l16 0"></path>
      <path d="M4 12l16 0"></path>
      <path d="M4 18l16 0"></path>
      </symbol>
      <symbol id="ti-file-spreadsheet" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="butt" strokeLinejoin="miter">
      <path d="M14 3v4a1 1 0 0 0 1 1h4"></path>
      <path d="M17 21h-10a2 2 0 0 1 -2 -2v-14a2 2 0 0 1 2 -2h7l5 5v11a2 2 0 0 1 -2 2"></path>
      <path d="M8 11h8v7h-8l0 -7"></path>
      <path d="M8 15h8"></path>
      <path d="M11 11v7"></path>
      </symbol>
      <symbol id="ti-file-type-pdf" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="butt" strokeLinejoin="miter">
      <path d="M14 3v4a1 1 0 0 0 1 1h4"></path>
      <path d="M5 12v-7a2 2 0 0 1 2 -2h7l5 5v4"></path>
      <path d="M5 18h1.5a1.5 1.5 0 0 0 0 -3h-1.5v6"></path>
      <path d="M17 18h2"></path>
      <path d="M20 15h-3v6"></path>
      <path d="M11 15v6h1a2 2 0 0 0 2 -2v-2a2 2 0 0 0 -2 -2h-1"></path>
      </symbol>
      <symbol id="ti-clock-hour-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="butt" strokeLinejoin="miter">
      <path d="M3 12a9 9 0 1 0 18 0a9 9 0 1 0 -18 0"></path>
      <path d="M12 12l3 2"></path>
      <path d="M12 7v5"></path>
      </symbol>
      <symbol id="ti-history" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="butt" strokeLinejoin="miter">
      <path d="M12 8l0 4l2 2"></path>
      <path d="M3.05 11a9 9 0 1 1 .5 4m-.5 5v-5h5"></path>
      </symbol>
      <symbol id="ti-filter" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="butt" strokeLinejoin="miter">
      <path d="M4 4h16v2.172a2 2 0 0 1 -.586 1.414l-4.414 4.414v7l-6 2v-8.5l-4.48 -4.928a2 2 0 0 1 -.52 -1.345v-2.227"></path>
      </symbol>
      <symbol id="ti-server-2" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="butt" strokeLinejoin="miter">
      <path d="M3 7a3 3 0 0 1 3 -3h12a3 3 0 0 1 3 3v2a3 3 0 0 1 -3 3h-12a3 3 0 0 1 -3 -3v-2"></path>
      <path d="M3 15a3 3 0 0 1 3 -3h12a3 3 0 0 1 3 3v2a3 3 0 0 1 -3 3h-12a3 3 0 0 1 -3 -3l0 -2"></path>
      <path d="M7 8l0 .01"></path>
      <path d="M7 16l0 .01"></path>
      <path d="M11 8h6"></path>
      <path d="M11 16h6"></path>
      </symbol>
      <symbol id="ti-device-cctv" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="butt" strokeLinejoin="miter">
      <path d="M3 4a1 1 0 0 1 1 -1h16a1 1 0 0 1 1 1v2a1 1 0 0 1 -1 1h-16a1 1 0 0 1 -1 -1l0 -2"></path>
      <path d="M8 14a4 4 0 1 0 8 0a4 4 0 1 0 -8 0"></path>
      <path d="M19 7v7a7 7 0 0 1 -14 0v-7"></path>
      <path d="M12 14l.01 0"></path>
      </symbol>
    </svg>
  );
}

type IconProps = {
  name: IconName;
  /** 14 / 18 / 20 / 24 — размеры из брендбука */
  size?: 14 | 18 | 20 | 24;
  style?: CSSProperties;
  className?: string;
};

export function Icon({ name, size = 20, style, className }: IconProps) {
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      className={className}
      style={{ width: size, height: size, flex: 'none', ...style }}
    >
      <use href={`#${name}`} />
    </svg>
  );
}
