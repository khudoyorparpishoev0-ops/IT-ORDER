import { useState } from 'react';
import { IthonaLogo } from '@/components/Logo';
import { api } from '@/api/client';
import { useAuthPolicy } from '@/api/auth';

/**
 * Восстановление пароля. Два экрана: запрос ссылки и ввод нового пароля
 * по ссылке из письма.
 *
 * Смена пароля не выдаёт сессию: второй фактор остаётся на месте, и войти
 * по одному лишь доступу к почте нельзя.
 */
export function PasswordReset({ token, onBack }: { token?: string; onBack: () => void }) {
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
      <div style={{ width: '100%', maxWidth: 400 }}>
        <div style={{ marginBottom: 24 }}>
          <IthonaLogo height={34} style={{ color: 'var(--logo)' }} />
          <div className="label" style={{ marginTop: 10 }}>
            ORDER
          </div>
        </div>
        {token ? <SetNewPassword token={token} onBack={onBack} /> : <RequestLink onBack={onBack} />}
      </div>
    </main>
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
      <div className="card">
        <div className="accent-rule" />
        <h1 className="h3" style={{ marginBottom: 4 }}>
          Проверьте почту
        </h1>
        {/* Не подтверждаем, заведён ли адрес: иначе перебором выясняется,
            кто есть в системе. */}
        <p className="caption" style={{ margin: '0 0 24px' }}>
          Если такой адрес заведён в системе, на него отправлено письмо со
          ссылкой. Ссылка действует ограниченное время и срабатывает один раз.
        </p>
        <button type="button" className="btn btn-secondary" onClick={onBack}>
          Вернуться ко входу
        </button>
      </div>
    );
  }

  return (
    <form className="card" onSubmit={submit} noValidate>
      <div className="accent-rule" />
      <h1 className="h3" style={{ marginBottom: 4 }}>
        Восстановление пароля
      </h1>
      <p className="caption" style={{ margin: '0 0 24px' }}>
        Пришлём ссылку на вашу корпоративную почту
      </p>

      <label style={{ display: 'block' }}>
        <div className="caption" style={{ marginBottom: 4 }}>
          Корпоративная почта
        </div>
        <input
          className={`field${error ? ' field-error' : ''}`}
          type="email"
          autoComplete="username"
          autoFocus
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder={`name${policy.data?.domains_hint ?? '@it-hona.tj'}`}
        />
      </label>

      {error && (
        <div className="field-error-text" role="alert" style={{ marginTop: 8 }}>
          {error}
        </div>
      )}

      <button
        type="submit"
        className="btn btn-primary"
        style={{ width: '100%', marginTop: 24 }}
        disabled={busy || !email}
      >
        {busy ? 'Отправляем…' : 'Прислать ссылку'}
      </button>
      <button
        type="button"
        className="btn btn-ghost"
        style={{ width: '100%', marginTop: 8 }}
        onClick={onBack}
      >
        Вернуться ко входу
      </button>
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
      <div className="card">
        <div className="accent-rule" />
        <h1 className="h3" style={{ marginBottom: 4 }}>
          Пароль изменён
        </h1>
        <p className="caption" style={{ margin: '0 0 24px' }}>
          Войдите с новым паролем. Если у вас включён двухфакторный вход, код
          из приложения понадобится как обычно.
        </p>
        <button type="button" className="btn btn-primary" onClick={onBack}>
          Перейти ко входу
        </button>
      </div>
    );
  }

  return (
    <form className="card" onSubmit={submit} noValidate>
      <div className="accent-rule" />
      <h1 className="h3" style={{ marginBottom: 4 }}>
        Новый пароль
      </h1>
      <p className="caption" style={{ margin: '0 0 24px' }}>
        Возьмите фразу от десяти символов: длинную проще запомнить и труднее
        подобрать
      </p>

      <label style={{ display: 'block', marginBottom: 16 }}>
        <div className="caption" style={{ marginBottom: 4 }}>
          Новый пароль
        </div>
        <input
          className={`field${error ? ' field-error' : ''}`}
          type="password"
          autoComplete="new-password"
          autoFocus
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </label>

      <label style={{ display: 'block' }}>
        <div className="caption" style={{ marginBottom: 4 }}>
          Повторите пароль
        </div>
        <input
          className={`field${error ? ' field-error' : ''}`}
          type="password"
          autoComplete="new-password"
          required
          value={repeat}
          onChange={(e) => setRepeat(e.target.value)}
        />
      </label>

      {error && (
        <div className="field-error-text" role="alert" style={{ marginTop: 8 }}>
          {error}
        </div>
      )}

      <button
        type="submit"
        className="btn btn-primary"
        style={{ width: '100%', marginTop: 24 }}
        disabled={busy || !password || !repeat}
      >
        {busy ? 'Сохраняем…' : 'Сохранить пароль'}
      </button>
      <button
        type="button"
        className="btn btn-ghost"
        style={{ width: '100%', marginTop: 8 }}
        onClick={onBack}
      >
        Вернуться ко входу
      </button>
    </form>
  );
}
