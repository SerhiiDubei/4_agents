import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';

export interface GameSummary {
  game: number;
  rounds: number;
  winner: string;
  scores: Record<string, number>;
}

export interface GamesSummaryResponse {
  games: GameSummary[];
  agentTotals: Record<string, number>;
  agentNames: string[];
  agentGamesPlayed?: Record<string, number>;
  agentRoundsPlayed?: Record<string, number>;
  agentAvgPerRound?: Record<string, number>;
}

export const LeaderboardView: React.FC<{ onBack?: () => void }> = ({ onBack }) => {
  const [data, setData] = useState<GamesSummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch('/api/games-summary')
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
          className="font-pixel text-game-cyan text-sm tracking-widest text-glow-cyan"
        >
          ЗАВАНТАЖЕННЯ ЛІДЕРБОРДУ...
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
            className="mt-6 font-pixel text-game-cyan border border-game-cyan px-6 py-3 text-sm tracking-widest box-glow-cyan"
          >
            [ НАЗАД ]
          </motion.button>
        )}
      </div>
    );
  }

  const { games, agentTotals, agentGamesPlayed = {}, agentRoundsPlayed = {}, agentAvgPerRound = {} } = data;
  const winsByAgent: Record<string, number> = {};
  games.forEach((g) => {
    const w = g.winner || '';
    if (w) winsByAgent[w] = (winsByAgent[w] ?? 0) + 1;
  });
  const names = [...new Set([...Object.keys(winsByAgent), ...Object.keys(agentTotals)])].filter(Boolean);
  // IDEA [REFACTOR: ЗБЕРЕГТИ]: Сортування за agentAvgPerRound (нормалізований 100=середній). Чесно для різної к-сті ігор.
  names.sort((a, b) => {
    const avgA = agentAvgPerRound[a] ?? 0;
    const avgB = agentAvgPerRound[b] ?? 0;
    if (avgB !== avgA) return avgB - avgA;
    const winsA = winsByAgent[a] ?? 0;
    const winsB = winsByAgent[b] ?? 0;
    if (winsB !== winsA) return winsB - winsA;
    return (agentTotals[b] ?? 0) - (agentTotals[a] ?? 0);
  });

  return (
    <div className="h-screen flex flex-col overflow-hidden bg-game-black relative z-10">
      <div className="flex-1 overflow-y-auto">
        <div className="flex flex-col items-center p-4 md:p-8 pb-12 min-h-full">
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            className="w-full max-w-4xl"
          >
            <div className="text-center mb-8">
              <h1 className="font-pixel text-game-gold text-sm md:text-base tracking-widest text-glow-cyan mb-2">
                ЛІДЕРБОРД
              </h1>
              <p className="font-dialog text-game-lightGray text-lg">
                Усереднено за раунд · перемоги · ігор · раундів
              </p>
            </div>

            <div className="overflow-x-auto rounded-sm border border-game-gold/50 bg-game-darkPurple/40 backdrop-blur-sm">
              <table className="w-full border-collapse table-fixed">
                <thead>
                  <tr>
                    <th className="font-pixel text-xs text-game-gold py-3 px-2 md:px-4 border-b border-game-gold/30 text-left">
                      #
                    </th>
                    <th className="font-pixel text-xs text-game-gold py-3 px-2 md:px-4 border-b border-game-gold/30 text-left">
                      АГЕНТ
                    </th>
                    <th className="font-pixel text-xs text-game-gold py-3 px-2 md:px-4 border-b border-game-gold/30 text-right">
                      ІГОР
                    </th>
                    <th className="font-pixel text-xs text-game-gold py-3 px-2 md:px-4 border-b border-game-gold/30 text-right">
                      РАУНДІВ
                    </th>
                    <th className="font-pixel text-xs text-game-gold py-3 px-2 md:px-4 border-b border-game-gold/30 text-right">
                      ПЕРЕМОГИ
                    </th>
                    <th className="font-pixel text-xs text-game-gold py-3 px-2 md:px-4 border-b border-game-gold/30 text-right">
                      ОЧОК/РАУНД
                    </th>
                    <th className="font-pixel text-xs text-game-gold py-3 px-2 md:px-4 border-b border-game-gold/30 text-right">
                      СУМА
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {names.map((name, idx) => {
                    const rounds = agentRoundsPlayed[name] ?? 0;
                    const avg = agentAvgPerRound[name] ?? 0;
                    return (
                      <motion.tr
                        key={name}
                        initial={{ opacity: 0, x: -8 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: idx * 0.03 }}
                        className="border-b border-game-gray/50 hover:bg-game-gold/5"
                      >
                        <td className="font-pixel text-game-cyan py-2 px-2 md:px-4 tabular-nums">
                          {idx + 1}
                        </td>
                        <td className="font-dialog text-game-lightGray py-2 px-2 md:px-4 font-bold">
                          {name}
                        </td>
                        <td className="font-pixel text-game-gold py-2 px-2 md:px-4 text-right tabular-nums">
                          {agentGamesPlayed[name] ?? 0}
                        </td>
                        <td className="font-pixel text-game-gold py-2 px-2 md:px-4 text-right tabular-nums">
                          {rounds}
                        </td>
                        <td className="font-pixel text-game-gold py-2 px-2 md:px-4 text-right tabular-nums">
                          {winsByAgent[name] ?? 0}
                        </td>
                        <td className="font-pixel text-game-lightGray py-2 px-2 md:px-4 text-right tabular-nums font-medium">
                          {rounds > 0 ? avg.toFixed(2) : '—'}
                        </td>
                        <td className="font-pixel text-game-lightGray py-2 px-2 md:px-4 text-right tabular-nums">
                          {(agentTotals[name] ?? 0).toFixed(2)}
                        </td>
                      </motion.tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {onBack && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.4 }}
                className="mt-8 flex justify-center"
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
