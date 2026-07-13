import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { authMe, authLogin, authRegister, setAuthInvalidCallback } from '../services/api';

const AuthContext = createContext(null);

const TOKEN_KEY = 'auth_token';

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    setUser(null);
  }, []);

  const login = useCallback(async (email, password) => {
    const res = await authLogin(email, password);
    const { token, user: u } = res;
    localStorage.setItem(TOKEN_KEY, token);
    setUser(u);
    return u;
  }, []);

  const register = useCallback(async (email, password, name) => {
    const res = await authRegister(email, password, name);
    const { token, user: u } = res;
    localStorage.setItem(TOKEN_KEY, token);
    setUser(u);
    return u;
  }, []);

  useEffect(() => {
    let cancelled = false;
    const token = localStorage.getItem(TOKEN_KEY);
    if (!token) {
      setLoading(false);
      return;
    }
    const AUTH_TIMEOUT_MS = 8000;
    const timeoutId = setTimeout(() => {
      if (!cancelled) {
        setLoading(false);
      }
    }, AUTH_TIMEOUT_MS);
    authMe()
      .then((data) => {
        if (!cancelled && data.user) setUser(data.user);
      })
      .catch(() => {
        if (!cancelled) localStorage.removeItem(TOKEN_KEY);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
        clearTimeout(timeoutId);
      });
    return () => {
      cancelled = true;
      clearTimeout(timeoutId);
    };
  }, []);

  // When 401 is returned, clear user so UI shows login again
  useEffect(() => {
    setAuthInvalidCallback(() => setUser(null));
    return () => setAuthInvalidCallback(null);
  }, []);

  const value = {
    user,
    loading,
    login,
    register,
    logout,
    isAuthenticated: !!user,
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
