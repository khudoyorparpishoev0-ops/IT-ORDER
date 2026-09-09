import type { ReactNode } from 'react';
import { Modal } from './Modal';

/**
 * Совместимая обёртка над Modal для форм, у которых заголовок внутри:
 * новые окна делать сразу на Modal с title и footer.
 */
export function Overlay({
  label,
  onClose,
  dirty = false,
  children,
}: {
  label: string;
  onClose: () => void;
  dirty?: boolean;
  children: ReactNode;
}) {
  return (
    <Modal title={label} onClose={onClose} dirty={dirty} wide>
      {children}
    </Modal>
  );
}
