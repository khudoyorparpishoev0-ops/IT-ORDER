import { useState } from 'react';
import { useAuth } from '@/api/auth';

/**
 * Вход. Единственный экран вне общего шелла: сайдбар без известного
 * пользователя показывать нечего.
 */
export function Login() {
  const { login, isLoggingIn } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await login({ email: email.trim(), password });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось войти');
    }
  };

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
          {/* Стенд-ин логотипа, как в сайдбаре. */}
          <div style={{ fontWeight: 800, letterSpacing: '0.06em', fontSize: 24 }}>
            IT-HONA
          </div>
          <div className="label" style={{ marginTop: 2 }}>
            CORE
          </div>
        </div>

        <form className="card" onSubmit={submit} noValidate>
          <div className="accent-rule" />
          <h1 className="h3" style={{ marginBottom: 4 }}>
            Вход в систему
          </h1>
          <p className="caption" style={{ margin: '0 0 24px' }}>
            Заявки на расходы сотрудников
          </p>

          <label style={{ display: 'block', marginBottom: 16 }}>
            <div className="caption" style={{ marginBottom: 4 }}>
              Рабочая почта
            </div>
            <input
              className="field"
              type="email"
              autoComplete="username"
              autoFocus
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="name@it-hona.tj"
            />
          </label>

          <label style={{ display: 'block' }}>
            <div className="caption" style={{ marginBottom: 4 }}>
              Пароль
            </div>
            <input
              className={`field${error ? ' field-error' : ''}`}
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              aria-invalid={Boolean(error)}
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
            disabled={isLoggingIn || !email || !password}
          >
            {isLoggingIn ? 'Проверяем…' : 'Войти'}
          </button>

          <p className="caption" style={{ margin: '16px 0 0' }}>
            Забыли пароль — обратитесь к администратору системы: сбросить его
            может только он.
          </p>
        </form>
      </div>
    </main>
  );
}
