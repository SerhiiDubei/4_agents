import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useAuth } from '../hooks/useAuth';

interface AuthModalProps {
  onClose: () => void;
}

type Tab = 'login' | 'register';

export const AuthModal: React.FC<AuthModalProps> = ({ onClose }) => {
  const { login, register, isLoading, error } = useAuth();
  const [tab, setTab] = useState<Tab>('login');

  // Поля форми
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [localError, setLocalError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLocalError('');

    if (tab === 'login') {
      if (!email || !password) { setLocalError('Введи email та пароль'); return; }
      const ok = await login(email, password);
      if (ok) onClose();
    } else {
      if (!username || !email || !password) { setLocalError('Заповни всі поля'); return; }
      if (password.length < 6) { setLocalError('Пароль мінімум 6 символів'); return; }
      const ok = await register(username, email, password);
      if (ok) onClose();
    }
  };

  const displayError = localError || error;

  return (
    // Backdrop
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-game-black/90 backdrop-blur-sm"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <motion.div
        initial={{ opacity: 0, y: -30, scale: 0.95 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 30, scale: 0.95 }}
        transition={{ type: 'spring', damping: 25, stiffness: 300 }}
        className="w-full max-w-sm mx-4 bg-game-black border border-game-cyan/40 p-8 relative"
        style={{ boxShadow: '0 0 40px rgba(0,240,255,0.15)' }}
      >
        {/* Кути в стилі CRT */}
        <div className="absolute top-0 left-0 w-4 h-4 border-t-2 border-l-2 border-game-cyan" />
        <div className="absolute top-0 right-0 w-4 h-4 border-t-2 border-r-2 border-game-cyan" />
        <div className="absolute bottom-0 left-0 w-4 h-4 border-b-2 border-l-2 border-game-cyan" />
        <div className="absolute bottom-0 right-0 w-4 h-4 border-b-2 border-r-2 border-game-cyan" />

        {/* Кнопка закрити */}
        <button
          onClick={onClose}
          className="absolute top-3 right-3 font-pixel text-game-lightGray text-xs hover:text-game-cyan transition-colors"
        >
          [X]
        </button>

        {/* Заголовок */}
        <div className="font-pixel text-game-cyan text-xs text-center mb-6 tracking-widest">
          ІДЕНТИФІКАЦІЯ АГЕНТА
        </div>

        {/* Таби */}
        <div className="flex mb-6 border-b border-game-gray">
          {(['login', 'register'] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => { setTab(t); setLocalError(''); }}
              className={`flex-1 font-pixel text-xs py-2 tracking-wider transition-colors ${
                tab === t
                  ? 'text-game-cyan border-b-2 border-game-cyan -mb-px'
                  : 'text-game-lightGray hover:text-white'
              }`}
            >
              {t === 'login' ? 'УВІЙТИ' : 'РЕЄСТРАЦІЯ'}
            </button>
          ))}
        </div>

        {/* Форма */}
        <form onSubmit={handleSubmit} className="space-y-4">
          <AnimatePresence mode="wait">
            {tab === 'register' && (
              <motion.div
                key="username-field"
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                className="overflow-hidden"
              >
                <label className="block font-pixel text-game-lightGray text-xs mb-1">
                  ІМ'Я АГЕНТА
                </label>
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="snake_77"
                  autoComplete="username"
                  className="w-full bg-game-gray/50 border border-game-gray text-white font-dialog text-lg px-3 py-2
                             focus:outline-none focus:border-game-cyan transition-colors placeholder-game-lightGray/40"
                />
              </motion.div>
            )}
          </AnimatePresence>

          <div>
            <label className="block font-pixel text-game-lightGray text-xs mb-1">EMAIL</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="agent@island.io"
              autoComplete="email"
              className="w-full bg-game-gray/50 border border-game-gray text-white font-dialog text-lg px-3 py-2
                         focus:outline-none focus:border-game-cyan transition-colors placeholder-game-lightGray/40"
            />
          </div>

          <div>
            <label className="block font-pixel text-game-lightGray text-xs mb-1">ПАРОЛЬ</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              autoComplete={tab === 'login' ? 'current-password' : 'new-password'}
              className="w-full bg-game-gray/50 border border-game-gray text-white font-dialog text-lg px-3 py-2
                         focus:outline-none focus:border-game-cyan transition-colors placeholder-game-lightGray/40"
            />
          </div>

          {displayError && (
            <div className="font-pixel text-game-red text-xs py-1 px-2 border border-game-red/40 bg-game-red/5">
              {displayError}
            </div>
          )}

          <motion.button
            type="submit"
            disabled={isLoading}
            whileHover={{ boxShadow: '0 0 20px rgba(0,240,255,0.4)' }}
            whileTap={{ scale: 0.97 }}
            className="w-full font-pixel text-xs text-game-cyan border-2 border-game-cyan py-3
                       bg-game-black/50 uppercase tracking-widest transition-all
                       hover:bg-game-cyan/10 disabled:opacity-40 disabled:cursor-not-allowed mt-2"
          >
            {isLoading
              ? 'ОБРОБКА...'
              : tab === 'login'
              ? '[ УВІЙТИ ]'
              : '[ СТВОРИТИ АКАУНТ ]'}
          </motion.button>
        </form>
      </motion.div>
    </motion.div>
  );
};
