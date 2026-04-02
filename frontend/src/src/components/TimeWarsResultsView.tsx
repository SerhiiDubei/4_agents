import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';

interface TwSession {
  sessionId: string;
  playedAt: string;
  winner: string;
  finalTimes: Record<string, number>;
  roles: Record<string, string>;
  reportPath: string;
  tick: number;
}

interface TwSummaryResponse {
  sessions: TwSession[];
  agentTotals: Record<string, number>;
  agentNames: string[];
}

const ROLE_LABELS: Record<string, string> = {
  role_peacekeeper: 'Миротворець',
  role_banker: 'Банкір',
  role_snake: 'Змія',
  role_gambler: 'Гемблер',
};

export const TimeWarsResultsView: React.FC<{ onBack?: () => void }> = ({ onBack }) => {
  const [data, setData] = useState<TwSummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch('/api/time-wars-summary')
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(res.statusText))))
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen p-8 bg-game-black relative z-10">
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="font-pixel text-emerald-400 text-sm tracking-widest"
        >
          ЗАВАНТАЖЕННЯ TIME WARS...
        </motion.div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen p-8 bg-game-black relative z-10">
        <p className="font-pixel text-game-red text-sm">{error || 'Немає даних'}</p>
        {onBack && (
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={onBack}
            className="mt-6 font-pixel text-emerald-400 border border-emerald-400 px-6 py-3 text-sm tracking-widest"
          >
            [ НАЗАД ]
          </motion.button>
        )}
      </div>
    );
  }

  const { sessions, agentTotals, agentNames } = data;
  const columns = agentNames.length > 0 ? agentNames : [...new Set(sessions.flatMap((s) => Object.keys(s.finalTimes)))];

  const bestTime = (name: string) => Math.max(...sessions.map((s) => s.finalTimes[name] ?? 0));

  return (
    <div className="h-screen flex flex-col overflow-hidden bg-game-black relative z-10">
      <div className="flex-1 overflow-y-auto">
        <div className="flex flex-col items-center p-4 md:p-8 pb-12 min-h-full">
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            className="w-full max-w-6xl"
          >
            <div className="text-center mb-8">
              <h1 className="font-pixel text-emerald-400 text-sm md:text-base tracking-widest mb-2">
                TIME WARS — РЕЗУЛЬТАТИ
              </h1>
              <p className="font-dialog text-game-lightGray text-lg">
                {sessions.length} сесій · секунди часу як ресурс
              </p>
            </div>

            {sessions.length === 0 ? (
              <div className="text-center py-16">
                <p className="font-pixel text-game-lightGray text-sm tracking-widest">
                  Немає завершених ігор. Запусти: <code className="text-emerald-400">python run_time_wars.py</code>
                </p>
              </div>
            ) : (
              <div className="overflow-x-auto rounded-sm border border-emerald-400/50 bg-game-darkPurple/40 backdrop-blur-sm mb-8">
                <table className="w-full border-collapse">
                  <thead>
                    <tr>
                      <th className="font-pixel text-xs text-emerald-400 py-3 px-2 md:px-4 border-b border-emerald-400/30 text-left">ЧАС</th>
                      <th className="font-pixel text-xs text-emerald-400 py-3 px-2 md:px-4 border-b border-emerald-400/30 text-left">ТІКІВ</th>
                      <th className="font-pixel text-xs text-emerald-400 py-3 px-2 md:px-4 border-b border-emerald-400/30 text-left">ПЕРЕМОЖЕЦЬ</th>
                      {columns.map((name) => (
                        <th key={name} className="font-pixel text-xs text-game-lightGray py-3 px-2 md:px-4 border-b border-emerald-400/30 text-right">
                          {name}
                        </th>
                      ))}
                      <th className="font-pixel text-xs text-emerald-400 py-3 px-2 md:px-4 border-b border-emerald-400/30 text-left">ЗВІТ</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sessions.map((s, idx) => (
                      <motion.tr
                        key={s.sessionId}
                        initial={{ opacity: 0, x: -8 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: idx * 0.03 }}
                        className="border-b border-game-gray/50 hover:bg-emerald-400/5"
                      >
                        <td className="font-dialog text-emerald-400/80 text-xs py-2 px-2 md:px-4 whitespace-nowrap">{s.playedAt}</td>
                        <td className="font-pixel text-xs text-game-lightGray py-2 px-2 md:px-4">{s.tick}</td>
                        <td className="font-dialog text-game-gold py-2 px-2 md:px-4 font-bold">{s.winner}</td>
                        {columns.map((name) => {
                          const val = s.finalTimes[name] ?? 0;
                          const isWinner = s.winner === name;
                          return (
                            <td key={name} className={`font-dialog py-2 px-2 md:px-4 text-right ${isWinner ? 'text-game-gold font-bold' : 'text-game-lightGray'}`}>
                              {val}с
                            </td>
                          );
                        })}
                        <td className="py-2 px-2 md:px-4">
                          <a
                            href={typeof window !== 'undefined' ? `${window.location.origin}${s.reportPath}` : s.reportPath}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="font-pixel text-xs text-emerald-400 border border-emerald-400/70 px-2 py-1 hover:bg-emerald-400/20 transition-colors"
                          >
                            ВІДКРИТИ
                          </a>
                        </td>
                      </motion.tr>
                    ))}
                    <tr className="border-t-2 border-emerald-400/50 bg-emerald-400/10">
                      <td colSpan={3} className="font-pixel text-xs text-game-pink py-3 px-2 md:px-4">
                        ЗАГАЛЬНИЙ ЧАС (сума всіх сесій)
                      </td>
                      {columns.map((name) => (
                        <td key={name} className="font-pixel text-xs text-game-gold py-3 px-2 md:px-4 text-right">
                          {agentTotals[name] ?? 0}с
                        </td>
                      ))}
                      <td />
                    </tr>
                    <tr className="bg-game-darkPurple/80 border-t border-emerald-400/30">
                      <td colSpan={3} className="font-pixel text-xs text-emerald-400 py-3 px-2 md:px-4">
                        РЕКОРД (найбільше секунд за гру)
                      </td>
                      {columns.map((name) => (
                        <td key={name} className="font-pixel text-xs text-emerald-400 py-3 px-2 md:px-4 text-right">
                          {bestTime(name)}с
                        </td>
                      ))}
                      <td />
                    </tr>
                  </tbody>
                </table>
              </div>
            )}

            {onBack && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.4 }}
                className="mt-4 flex justify-center"
              >
                <motion.button
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  onClick={onBack}
                  className="font-pixel text-game-lightGray border border-game-lightGray/50 px-8 py-4 text-sm tracking-widest hover:bg-game-lightGray/10"
                >
                  [ НАЗАД ]
                </motion.button>
              </motion.div>
            )}
          </motion.div>
        </div>
      </div>
    </div>
  );
};
