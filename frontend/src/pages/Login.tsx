import { useState } from 'react';
import { Field } from '@/components/Field';
import { useAuth, useAuthPolicy } from '@/api/auth';
import { useSessionExpired } from '@/api/session';
import { TotpSetup } from '@/components/TotpSetup';
import { AuthScreen, PasswordReset } from './PasswordReset';

/**
 * Вход. Единственный экран вне общего шелла: сайдбар без известного
 * пользователя показывать нечего.
 *
 * Шагов может быть два: почта с паролем, затем код из приложения.
 * Ролям, которым второй фактор обязателен, вместо кода показывается
 * настройка — иначе они не смогли бы войти вообще.
 */
export function Login() {
  const sessionExpired = useSessionExpired();
  const { login, submitCode, pending, cancelPending, finishPendingSetup, isBusy } =
    useAuth();
  const policy = useAuthPolicy();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');
  const [error, setError] = useState<string | null>(null);
  // Ссылка из письма приходит с токеном в адресе.
  const resetToken = new URLSearchParams(window.location.search).get('token');
  const [recovering, setRecovering] = useState(
    window.location.pathname === '/reset-password',
  );

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

  if (recovering) {
    return (
      <PasswordReset
        token={resetToken ?? undefined}
        onBack={() => {
          setRecovering(false);
          // Токен из адреса убираем: перезагрузка не должна снова
          // открывать форму смены пароля по использованной ссылке.
          window.history.replaceState(null, '', '/');
        }}
      />
    );
  }

  return (
    <AuthScreen wide={pending === '2fa_setup_required'}>
      {sessionExpired && pending === null && (
        <div
          role="status"
          className="card card-accent small"
          style={{ ['--accent' as string]: 'var(--yellow)', padding: 16 }}
        >
          Сессия истекла — войдите заново. Если вы что-то заполняли, эти
          данные не сохранились: их придётся ввести ещё раз.
        </div>
      )}

      {pending === null && (
        <form className="card" onSubmit={submitCredentials} noValidate style={{ display: 'grid', gap: 16 }}>
          <div>
            <h1 className="h3">Вход в систему</h1>
            <p className="caption" style={{ margin: '4px 0 0' }}>
              Заявки на расходы сотрудников
            </p>
          </div>

          <Field label="Корпоративная почта" required>
            {(id) => (
              <input
                id={id}
                className="field"
                type="email"
                autoComplete="username"
                autoFocus
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder={`name${policy.data?.domains_hint ?? '@it-hona.tj'}`}
              />
            )}
          </Field>

          <Field label="Пароль" required error={error}>
            {(id) => (
              <input
                id={id}
                className={`field${error ? ' field-error' : ''}`}
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                aria-invalid={Boolean(error)}
              />
            )}
          </Field>

          <div style={{ display: 'grid', gap: 8, marginTop: 8 }}>
            <button
              type="submit"
              className="btn btn-primary btn-block"
              disabled={isBusy || !email || !password}
            >
              {isBusy ? 'Проверяем…' : 'Войти'}
            </button>

            {policy.data?.password_reset_available && (
              <button
                type="button"
                className="btn btn-ghost btn-block"
                onClick={() => setRecovering(true)}
              >
                Забыли пароль?
              </button>
            )}
          </div>

          <p className="caption" style={{ margin: 0 }}>
            Вход только с корпоративной почты
            {policy.data?.domains_hint ? ` (${policy.data.domains_hint})` : ''}.
            {!policy.data?.password_reset_available &&
              ' Забыли пароль — обратитесь к администратору системы.'}
          </p>
        </form>
      )}

      {pending === '2fa_required' && (
        <form className="card" onSubmit={submitSecondFactor} noValidate style={{ display: 'grid', gap: 16 }}>
          <div>
            <h1 className="h3">Код подтверждения</h1>
            <p className="caption" style={{ margin: '4px 0 0' }}>
              Откройте приложение-аутентификатор и введите шестизначный код
            </p>
          </div>

          <Field label="Код из приложения" required error={error}>
            {(id) => (
              <input
                id={id}
                className={`field mono${error ? ' field-error' : ''}`}
                inputMode="numeric"
                autoComplete="one-time-code"
                autoFocus
                required
                value={code}
                onChange={(e) => setCode(e.target.value)}
                aria-invalid={Boolean(error)}
                placeholder="000000"
                style={{ letterSpacing: '0.2em' }}
              />
            )}
          </Field>

          <div style={{ display: 'grid', gap: 8, marginTop: 8 }}>
            <button
              type="submit"
              className="btn btn-primary btn-block"
              disabled={isBusy || !code}
            >
              {isBusy ? 'Проверяем…' : 'Подтвердить'}
            </button>

            <button type="button" className="btn btn-ghost btn-block" onClick={startOver}>
              Войти под другой учётной записью
            </button>
          </div>

          <p className="caption" style={{ margin: 0 }}>
            Потеряли телефон — введите один из кодов восстановления. Если их
            тоже нет, второй фактор сбросит администратор.
          </p>
        </form>
      )}

      {pending === '2fa_setup_required' && (
        <div className="card" style={{ display: 'grid', gap: 16 }}>
          <div>
            <h1 className="h3">Требуется двухфакторный вход</h1>
            <p className="caption" style={{ margin: '4px 0 0' }}>
              Для вашей роли одного пароля недостаточно. Настройте приложение —
              это занимает минуту и делается один раз.
            </p>
          </div>
          {/* На панель переходим только после того, как человек
              подтвердит, что сохранил коды восстановления. */}
          <TotpSetup onCancel={startOver} onDone={finishPendingSetup} />
        </div>
      )}
    </AuthScreen>
  );
}
