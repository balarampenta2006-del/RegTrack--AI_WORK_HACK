import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { useNavigate } from 'react-router-dom';
import { api, loginRequest, tokenStore, UNAUTHORIZED_EVENT, userStore } from '../api/client';
import type { User } from '../api/types';

interface AuthContextValue {
  user: User | null;
  ready: boolean;
  isAdmin: boolean;
  login: (email: string, password: string) => Promise<User>;
  logout: () => void;
  setUser: (user: User) => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const [user, setUserState] = useState<User | null>(() => userStore.get());
  const [ready, setReady] = useState<boolean>(() => tokenStore.get() === null);

  useEffect(() => {
    if (tokenStore.get() === null) {
      setReady(true);
      return;
    }
    let active = true;
    api
      .get<User>('/api/me')
      .then((me) => {
        if (!active) return;
        userStore.set(me);
        setUserState(me);
      })
      .catch(() => {
        if (!active) return;
        setUserState(null);
      })
      .finally(() => {
        if (active) setReady(true);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    const onUnauthorized = () => {
      setUserState(null);
      setReady(true);
      navigate('/login', { replace: true });
    };
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
  }, [navigate]);

  const login = useCallback(async (email: string, password: string): Promise<User> => {
    const auth = await loginRequest(email, password);
    tokenStore.set(auth.token);
    userStore.set(auth.user);
    setUserState(auth.user);
    return auth.user;
  }, []);

  const logout = useCallback(() => {
    tokenStore.clear();
    setUserState(null);
    navigate('/login', { replace: true });
  }, [navigate]);

  const setUser = useCallback((next: User) => {
    userStore.set(next);
    setUserState(next);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      ready,
      isAdmin: user?.role === 'ADMIN',
      login,
      logout,
      setUser,
    }),
    [user, ready, login, logout, setUser],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used inside <AuthProvider>');
  return context;
}
