import { useState } from 'react';
import { useAuth, useAuthPolicy } from '@/api/auth';
import { TotpSetup } from '@/components/TotpSetup';

/**
 * Вход. Единственный экран вне общего шелла: сайдбар без известного
 * пользователя показывать нечего.
 *
 * Шагов может быть два: почта с паролем, затем код из приложения.
 * Ролям, которым второй фактор обязателен, вместо кода показывается
 * настройка — иначе они не смогли бы войти вообще.
 */
export function Login() {
  const { login, submitCode, pending, cancelPending, finishPendingSetup, isBusy } =
    useAuth();
  const policy = useAuthPolicy();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');
  const [error, setError] = useState<string | null>(null);

  const fail = (err: unknown, fallback: string) =>
    setError(err instanceof Error ? err.message : fallback);

  const submitCredentials = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await login({ email: email.trim(), password });
    } catch (err) {
      fail(err, 'Не удалось войти');
    }
  };

  const submitSecondFactor = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await submitCode(code.trim());
    } catch (err) {
      setCode('');
      fail(err, 'Код не подошёл');
    }
  };

  const startOver = async () => {
    setError(null);
    setCode('');
    setPassword('');
    await cancelPending();
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
      <div style={{ width: '100%', maxWidth: pending === '2fa_setup_required' ? 520 : 400 }}>
        <div style={{ marginBottom: 24 }}>
          {/* Стенд-ин логотипа, как в сайдбаре. */}
          <div style={{ fontWeight: 800, letterSpacing: '0.06em', fontSize: 24 }}>
            IT-HONA
          </div>
          <div className="label" style={{ marginTop: 2 }}>
            CORE
          </div>
        </div>

        {pending === null && (
          <form className="card" onSubmit={submitCredentials} noValidate>
            <div className="accent-rule" />
            <h1 className="h3" style={{ marginBottom: 4 }}>
              Вход в систему
            </h1>
            <p className="caption" style={{ margin: '0 0 24px' }}>
              Заявки на расходы сотрудников
            </p>

            <label style={{ display: 'block', marginBottom: 16 }}>
              <div className="caption" style={{ marginBottom: 4 }}>
                Корпоративная почта
              </div>
              <input
                className="field"
                type="email"
                autoComplete="username"
                autoFocus
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder={`name${policy.data?.domains_hint ?? '@it-hona.tj'}`}
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
              disabled={isBusy || !email || !password}
            >
              {isBusy ? 'Проверяем…' : 'Войти'}
            </button>

            <p className="caption" style={{ margin: '16px 0 0' }}>
              Вход только с корпоративной почты{' '}
              {policy.data?.domains_hint ? `(${policy.data.domains_hint})` : ''}. Забыли
              пароль — обратитесь к администратору системы.
            </p>
          </form>
        )}

        {pending === '2fa_required' && (
          <form className="card" onSubmit={submitSecondFactor} noValidate>
            <div className="accent-rule" />
            <h1 className="h3" style={{ marginBottom: 4 }}>
              Код подтверждения
            </h1>
            <p className="caption" style={{ margin: '0 0 24px' }}>
              Откройте приложение-аутентификатор и введите шестизначный код
            </p>

            <label style={{ display: 'block' }}>
              <div className="caption" style={{ marginBottom: 4 }}>
                Код из приложения
              </div>
              <input
                className={`field${error ? ' field-error' : ''}`}
                inputMode="numeric"
                autoComplete="one-time-code"
                autoFocus
                required
                value={code}
                onChange={(e) => setCode(e.target.value)}
                aria-invalid={Boolean(error)}
                placeholder="000000"
                style={{ fontFamily: 'var(--font-mono)', letterSpacing: '0.2em' }}
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
              disabled={isBusy || !code}
            >
              {isBusy ? 'Проверяем…' : 'Подтвердить'}
            </button>

            <button
              type="button"
              className="btn btn-ghost"
              style={{ width: '100%', marginTop: 8 }}
              onClick={startOver}
            >
              Войти под другой учётной записью
            </button>

            <p className="caption" style={{ margin: '16px 0 0' }}>
              Потеряли телефон — введите один из кодов восстановления. Если их
              тоже нет, второй фактор сбросит администратор.
            </p>
          </form>
        )}

        {pending === '2fa_setup_required' && (
          <div className="card">
            <div className="accent-rule" />
            <h1 className="h3" style={{ marginBottom: 4 }}>
              Требуется двухфакторный вход
            </h1>
            <p className="caption" style={{ margin: '0 0 24px' }}>
              Для вашей роли одного пароля недостаточно. Настройте приложение —
              это занимает минуту и делается один раз.
            </p>
            {/* На панель переходим только после того, как человек
                подтвердит, что сохранил коды восстановления. */}
            <TotpSetup onCancel={startOver} onDone={finishPendingSetup} />
          </div>
        )}
      </div>
    </main>
  );
}
