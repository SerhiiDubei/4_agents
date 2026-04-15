import { useState, useCallback, useEffect } from 'react';

// Дані користувача після успішного входу
export interface AuthUser {
  userId: string;
  username: string;
  token: string;
}

const STORAGE_KEY = 'agents_auth_token';
const STORAGE_USER = 'agents_auth_user';

// Зберігаємо токен і дані у localStorage
function saveAuth(user: AuthUser): void {
  localStorage.setItem(STORAGE_KEY, user.token);
  localStorage.setItem(STORAGE_USER, JSON.stringify({ userId: user.userId, username: user.username }));
}

function loadAuth(): AuthUser | null {
  const token = localStorage.getItem(STORAGE_KEY);
  const raw = localStorage.getItem(STORAGE_USER);
  if (!token || !raw) return null;
  try {
    const { userId, username } = JSON.parse(raw);
    return { token, userId, username };
  } catch {
    return null;
  }
}

function clearAuth(): void {
  localStorage.removeItem(STORAGE_KEY);
  localStorage.removeItem(STORAGE_USER);
}

export interface UseAuthReturn {
  user: AuthUser | null;
  isLoading: boolean;
  error: string;
  login: (email: string, password: string) => Promise<boolean>;
  register: (username: string, email: string, password: string) => Promise<boolean>;
  logout: () => void;
}

export function useAuth(): UseAuthReturn {
  const [user, setUser] = useState<AuthUser | null>(() => loadAuth());
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  // Верифікуємо токен при старті — якщо протух, чистимо
  useEffect(() => {
    const stored = loadAuth();
    if (!stored) return;
    fetch('/auth/me', {
      headers: { Authorization: `Bearer ${stored.token}` },
    }).then((res) => {
      if (!res.ok) {
        clearAuth();
        setUser(null);
      }
    }).catch(() => {
      // Мережева помилка — залишаємо кеш (офлайн-ситуація)
    });
  }, []);

  const login = useCallback(async (email: string, password: string): Promise<boolean> => {
    setIsLoading(true);
    setError('');
    try {
      const res = await fetch('/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.detail || 'Помилка входу');
        return false;
      }
      const authUser: AuthUser = {
        token: data.access_token,
        userId: data.user_id,
        username: data.username,
      };
      saveAuth(authUser);
      setUser(authUser);
      return true;
    } catch {
      setError('Помилка мережі');
      return false;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const register = useCallback(async (username: string, email: string, password: string): Promise<boolean> => {
    setIsLoading(true);
    setError('');
    try {
      const res = await fetch('/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, email, password }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.detail || 'Помилка реєстрації');
        return false;
      }
      const authUser: AuthUser = {
        token: data.access_token,
        userId: data.user_id,
        username: data.username,
      };
      saveAuth(authUser);
      setUser(authUser);
      return true;
    } catch {
      setError('Помилка мережі');
      return false;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const logout = useCallback(() => {
    clearAuth();
    setUser(null);
    setError('');
  }, []);

  return { user, isLoading, error, login, register, logout };
}
