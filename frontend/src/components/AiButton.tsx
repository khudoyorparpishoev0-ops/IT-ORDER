import { Icon } from '@/components/Icon';

type Props = {
  /** Есть ли что отправлять помощнику. Пусто — кнопка серая. */
  active: boolean;
  /** Ждём ответ модели. Кнопка занята и говорит об этом словом. */
  busy?: boolean;
  label: string;
  /** Подпись во время ожидания. По умолчанию «Думаю…». */
  busyLabel?: string;
  type?: 'button' | 'submit';
  small?: boolean;
  disabled?: boolean;
  onClick?: () => void;
};

/**
 * Кнопка помощника. Три состояния, и все три — состояния кнопки, а не
 * отдельные элементы: серая, пока отправлять нечего; зелёная, как только
 * человеку есть что спросить; занятая, пока модель думает.
 *
 * Зелёной она становится именно от наличия текста: ответ помощника — это
 * десятки секунд и деньги, и звать его вхолостую не за что. Занятая
 * кнопка не исчезает и не подменяется спиннером: пропавшая кнопка
 * читается как сбой, а подпись «Думаю…» объясняет ожидание словами.
 */
export function AiButton({
  active,
  busy = false,
  label,
  busyLabel = 'Думаю…',
  type = 'button',
  small = false,
  disabled = false,
  onClick,
}: Props) {
  return (
    <button
      type={type}
      className={`btn ${active && !busy ? 'btn-primary' : 'btn-secondary'}${small ? ' btn-sm' : ''}`}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      onClick={onClick}
    >
      <Icon name={busy ? 'ti-clock-hour-4' : 'ti-sparkles'} size={small ? 14 : 18} />
      {busy ? busyLabel : label}
    </button>
  );
}
