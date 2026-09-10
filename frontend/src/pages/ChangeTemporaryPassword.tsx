import { useState } from 'react';
import { Field } from '@/components/Field';
import { api } from '@/api/client';
import { useAuth } from '@/api/auth';
import { AuthScreen } from './PasswordReset';

/**
 * Экран обязательной смены временного пароля.
 *
 * Пароль, выданный администратором, знают двое. Работать под ним нельзя:
 * заявка, поданная так, не доказывает, кто её подал. Поэтому сервер
 * закрывает всё, кроме этого экрана, — а панель показывает его вместо
 * шелла целиком, чтобы человек не искал, где сменить пароль.
 *
 * Кнопки «пропустить» здесь нет намеренно: единственный выход — задать
 * свой пароль или выйти.
 */
export function ChangeTemporaryPassword() {
  const { user, logout, refresh } = useAuth();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [repeat, setRepeat] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (next !== repeat) {
      setError('Пароли не совпадают');
      return;
    }
    setError(null);
    setBusy(true);
    try {
      await api('/api/auth/password', {
        method: 'POST',
        body: JSON.stringify({ current_password: current, new_password: next }),
      });
      // Смена пароля гасит и эту сессию — заново входит уже человек со
      // своим паролем. Обновляем состояние, экран входа покажется сам.
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось сменить пароль');
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthScreen>
      <form className="card" onSubmit={submit} noValidate style={{ display: 'grid', gap: 16 }}>
        <div>
          <h1 className="h3">Задайте свой пароль</h1>
          <p className="caption" style={{ margin: '4px 0 0' }}>
            {user?.full_name}, ваш нынешний пароль выдан администратором и известен
            не только вам. Работа в системе откроется, когда вы замените его своим.
          </p>
        </div>

        <Field label="Временный пароль" required>
          {(id) => (
            <input
              id={id}
              className="field"
              type="password"
              autoComplete="current-password"
              autoFocus
              required
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
            />
          )}
        </Field>

        <Field
          label="Новый пароль"
          required
          note="Возьмите фразу от десяти символов: длинную проще запомнить и труднее подобрать"
        >
          {(id) => (
            <input
              id={id}
              className={`field${error ? ' field-error' : ''}`}
              type="password"
              autoComplete="new-password"
              required
              value={next}
              onChange={(e) => setNext(e.target.value)}
              aria-invalid={Boolean(error)}
            />
          )}
        </Field>

        <Field label="Повторите новый пароль" required error={error}>
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
            disabled={busy || !current || !next || !repeat}
          >
            {busy ? 'Сохраняем…' : 'Сохранить и продолжить'}
          </button>
          <button type="button" className="btn btn-ghost btn-block" onClick={() => logout()}>
            Выйти
          </button>
        </div>
      </form>
    </AuthScreen>
  );
}
