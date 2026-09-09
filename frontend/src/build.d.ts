/** Дата сборки, подставляется Vite (см. vite.config.ts). */
declare const __BUILD_DATE__: string;

/** Признак production-сборки от Vite: в dev service worker не регистрируем. */
interface ImportMeta {
  readonly env: { readonly PROD: boolean; readonly DEV: boolean };
}
