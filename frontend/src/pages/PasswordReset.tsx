import { useState } from 'react';
import { Field } from '@/components/Field';
import { api } from '@/api/client';
import { useAuthPolicy } from '@/api/auth';
import { OrderLogoStacked } from '@/components/Logo';

/**
 * Восстановление пароля. Два экрана: запрос ссылки и ввод нового пароля
 * по ссылке из письма.
 *
 * Смена пароля не выдаёт сессию: второй фактор остаётся на месте, и войти
 * по одному лишь доступу к почте нельзя.
 */
export function PasswordReset({ token, onBack }: { token?: string; onBack: () => void }) {
  return (
    <AuthScreen>
      {token ? <SetNewPassword token={token} onBack={onBack} /> : <RequestLink onBack={onBack} />}
    </AuthScreen>
  );
}

/** Шапка карточки входа: заголовок и подпись под ним. */
function CardHead({ title, note }: { title: string; note: string }) {
  return (
    <div>
      <h1 className="h3">{title}</h1>
      <p className="caption" style={{ margin: '4px 0 0' }}>
        {note}
      </p>
    </div>
  );
}

function RequestLink({ onBack }: { onBack: () => void }) {
  const policy = useAuthPolicy();
  const [email, setEmail] = useState('');
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api('/api/auth/password-reset/request', {
        method: 'POST',
        body: JSON.stringify({ email: email.trim() }),
      });
      setSent(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось отправить письмо');
    } finally {
      setBusy(false);
    }
  };

  if (sent) {
    return (
      <div className="card" style={{ display: 'grid', gap: 16 }}>
        {/* Не подтверждаем, заведён ли адрес: иначе перебором выясняется,
            кто есть в системе. */}
        <CardHead
          title="Проверьте почту"
          note="Если такой адрес заведён в системе, на него отправлено письмо со ссылкой. Ссылка действует ограниченное время и срабатывает один раз."
        />
        <button type="button" className="btn btn-secondary btn-block" onClick={onBack}>
          Вернуться ко входу
        </button>
      </div>
    );
  }

  return (
    <form className="card" onSubmit={submit} noValidate style={{ display: 'grid', gap: 16 }}>
      <CardHead title="Восстановление пароля" note="Пришлём ссылку на вашу корпоративную почту" />

      <Field label="Корпоративная почта" required error={error}>
        {(id) => (
          <input
            id={id}
            className={`field${error ? ' field-error' : ''}`}
            type="email"
            autoComplete="username"
            autoFocus
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            aria-invalid={Boolean(error)}
            placeholder={`name${policy.data?.domains_hint ?? '@it-hona.tj'}`}
          />
        )}
      </Field>

      <div style={{ display: 'grid', gap: 8, marginTop: 8 }}>
        <button type="submit" className="btn btn-primary btn-block" disabled={busy || !email}>
          {busy ? 'Отправляем…' : 'Прислать ссылку'}
        </button>
        <button type="button" className="btn btn-ghost btn-block" onClick={onBack}>
          Вернуться ко входу
        </button>
      </div>
    </form>
  );
}

function SetNewPassword({ token, onBack }: { token: string; onBack: () => void }) {
  const [password, setPassword] = useState('');
  const [repeat, setRepeat] = useState('');
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (password !== repeat) {
      setError('Пароли не совпадают');
      return;
    }
    setError(null);
    setBusy(true);
    try {
      await api('/api/auth/password-reset/confirm', {
        method: 'POST',
        body: JSON.stringify({ token, new_password: password }),
      });
      setDone(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось сменить пароль');
    } finally {
      setBusy(false);
    }
  };

  if (done) {
    return (
      <div className="card" style={{ display: 'grid', gap: 16 }}>
        <CardHead
          title="Пароль изменён"
          note="Войдите с новым паролем. Если у вас включён двухфакторный вход, код из приложения понадобится как обычно."
        />
        <button type="button" className="btn btn-primary btn-block" onClick={onBack}>
          Перейти ко входу
        </button>
      </div>
    );
  }

  return (
    <form className="card" onSubmit={submit} noValidate style={{ display: 'grid', gap: 16 }}>
      <CardHead
        title="Новый пароль"
        note="Возьмите фразу от десяти символов: длинную проще запомнить и труднее подобрать"
      />

      <Field label="Новый пароль" required>
        {(id) => (
          <input
            id={id}
            className={`field${error ? ' field-error' : ''}`}
            type="password"
            autoComplete="new-password"
            autoFocus
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            aria-invalid={Boolean(error)}
          />
        )}
      </Field>

      <Field label="Повторите пароль" required error={error}>
        {(id) => (
          <input
            id={id}
            className={`field${error ? ' field-error' : ''}`}
            type="password"
            autoComplete="new-password"
            required
            value={repeat}
            onChange={(e) => setRepeat(e.target.value)}
            aria-invalid={Boolean(error)}
          />
        )}
      </Field>

      <div style={{ display: 'grid', gap: 8, marginTop: 8 }}>
        <button
          type="submit"
          className="btn btn-primary btn-block"
          disabled={busy || !password || !repeat}
        >
          {busy ? 'Сохраняем…' : 'Сохранить пароль'}
        </button>
        <button type="button" className="btn btn-ghost btn-block" onClick={onBack}>
          Вернуться ко входу
        </button>
      </div>
    </form>
  );
}

/**
 * Общая рамка экранов вне шелла: колонка по центру на фоне mist, сверху
 * фирменный логотип. Её же берёт экран входа (Login).
 */
export function AuthScreen({ wide = false, children }: { wide?: boolean; children: React.ReactNode }) {
  return (
    <main
      style={{
        minHeight: '100vh',
        display: 'grid',
        placeItems: 'center',
        padding: 16,
        background: 'var(--mist)',
      }}
    >
      <div style={{ width: '100%', maxWidth: wide ? 520 : 400, display: 'grid', gap: 16 }}>
        <div style={{ marginBottom: 8 }}>
          <OrderLogoStacked height={96} style={{ color: 'var(--logo)' }} />
        </div>
        {children}
      </div>
    </main>
  );
}
