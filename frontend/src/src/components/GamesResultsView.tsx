import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';

export interface GameSummary {
  game: number;
  rounds: number;
  winner: string;
  scores: Record<string, number>;
  reportPath: string;
  runId: string;
  runLabel: string;
  playedAt?: string;
}

export interface RunSummary {
  runId: string;
  runLabel: string;
  runTitle: string;
  gameCount: number;
}

export interface GamesSummaryResponse {
  games: GameSummary[];
  runs: RunSummary[];
  agentTotals: Record<string, number>;
  agentNames: string[];
  /** IDEA: API віддає нормалізований середній (100=середній по грі). Потрібен для GamesResultsView. */
  agentRoundsPlayed?: Record<string, number>;
  agentAvgPerRound?: Record<string, number>;
}

export const GamesResultsView: React.FC<{ onBack?: () => void }> = ({ onBack }) => {
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
          ЗАВАНТАЖЕННЯ РЕЗУЛЬТАТІВ...
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

  const { games, agentTotals, agentNames, agentRoundsPlayed = {}, agentAvgPerRound = {} } = data;
  const columns = agentNames.length > 0 ? agentNames : [...new Set(games.flatMap((g) => Object.keys(g.scores)))];
  const totalRounds = games.reduce((sum, g) => sum + (g.rounds || 0), 0);
  /* IDEA [REFACTOR: ЗБЕРЕГТИ]: Використовуй agentAvgPerRound з API (нормалізований). Fallback — тільки для legacy. */
  const averageScore = (name: string) => {
    const avg = agentAvgPerRound[name];
    if (avg != null) return avg;
    const rnd = agentRoundsPlayed[name] ?? 0;
    return rnd > 0 ? (agentTotals[name] ?? 0) / rnd : 0;
  };

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
              <h1 className="font-pixel text-game-cyan text-sm md:text-base tracking-widest text-glow-cyan mb-2">
                РЕЗУЛЬТАТИ ІГОР
              </h1>
              <p className="font-dialog text-game-lightGray text-lg">Усі ігри в одній таблиці · очки та загальний бал</p>
            </div>

            <div className="overflow-x-auto rounded-sm border border-game-cyan/50 box-glow-cyan bg-game-darkPurple/40 backdrop-blur-sm">
              {/* IDEA: min-w-max + whitespace-nowrap на числах — без цього колонки зливаються */}
              <table className="w-full border-collapse min-w-max">
                <thead>
                  <tr>
                    <th className="font-pixel text-xs text-game-cyan py-3 px-2 md:px-4 border-b border-game-cyan/30 text-left">
                      ЧАС
                    </th>
                    <th className="font-pixel text-xs text-game-cyan py-3 px-2 md:px-4 border-b border-game-cyan/30 text-left">
                      ГРА
                    </th>
                    <th className="font-pixel text-xs text-game-cyan py-3 px-2 md:px-4 border-b border-game-cyan/30 text-left">
                      РАУНДІВ
                    </th>
                    <th className="font-pixel text-xs text-game-cyan py-3 px-2 md:px-4 border-b border-game-cyan/30 text-left">
                      ПЕРЕМОЖЕЦЬ
                    </th>
                    {columns.map((name) => (
                      <th
                        key={name}
                        className="font-pixel text-xs text-game-lightGray py-3 px-2 md:px-4 border-b border-game-cyan/30 text-right whitespace-nowrap"
                      >
                        {name}
                      </th>
                    ))}
                    <th className="font-pixel text-xs text-game-cyan py-3 px-2 md:px-4 border-b border-game-cyan/30 text-left">
                      ЗВІТ
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {games.map((row, idx) => (
                    <motion.tr
                      key={`${row.runId}-${row.game}-${idx}`}
                      initial={{ opacity: 0, x: -8 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: idx * 0.02 }}
                      className="border-b border-game-gray/50 hover:bg-game-cyan/5"
                    >
                      <td className="font-dialog text-game-cyan/90 text-xs py-2 px-2 md:px-4 whitespace-nowrap">
                        {row.playedAt ?? row.runLabel}
                      </td>
                      <td className="font-pixel text-xs text-game-pink py-2 px-2 md:px-4">{row.game}</td>
                      <td className="font-dialog text-game-lightGray py-2 px-2 md:px-4">{row.rounds}</td>
                      <td className="font-dialog text-game-gold py-2 px-2 md:px-4 font-bold">{row.winner}</td>
                      {/* IDEA: tabular-nums + font-pixel + whitespace-nowrap — без цього числа зливаються в колонках */}
                      {columns.map((name) => (
                        <td key={name} className="font-pixel text-game-lightGray py-2 px-2 md:px-4 text-right tabular-nums whitespace-nowrap">
                          {(row.scores[name] ?? 0).toFixed(2)}
                        </td>
                      ))}
                      <td className="py-2 px-2 md:px-4">
                        <a
                          href={typeof window !== 'undefined' ? `${window.location.origin}${row.reportPath}` : row.reportPath}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="font-pixel text-xs text-game-cyan border border-game-cyan/70 px-2 py-1 hover:bg-game-cyan/20 transition-colors"
                        >
                          ВІДКРИТИ
                        </a>
                      </td>
                    </motion.tr>
                  ))}
                  <tr className="border-t-2 border-game-cyan/50 bg-game-cyan/10">
                    <td colSpan={4} className="font-pixel text-xs text-game-pink py-3 px-2 md:px-4">
                      ЗАГАЛЬНИЙ БАЛ (усі ігри)
                    </td>
                    {columns.map((name) => (
                      <td key={name} className="font-pixel text-xs text-game-gold py-3 px-2 md:px-4 text-right tabular-nums whitespace-nowrap">
                        {(agentTotals[name] ?? 0).toFixed(2)}
                      </td>
                    ))}
                    <td className="py-3 px-2 md:px-4" />
                  </tr>
                  <tr className="bg-game-darkPurple/80 border-t border-game-cyan/30">
                    <td colSpan={4} className="font-pixel text-xs text-game-cyan py-3 px-2 md:px-4">
                      СЕРЕДНІЙ БАЛ (норм. 100=середній, усереднено за ігри)
                    </td>
                    {columns.map((name) => (
                      <td key={name} className="font-pixel text-xs text-game-cyan py-3 px-2 md:px-4 text-right tabular-nums whitespace-nowrap">
                        {averageScore(name).toFixed(2)}
                      </td>
                    ))}
                    <td className="py-3 px-2 md:px-4 font-dialog text-game-lightGray text-xs">
                      {totalRounds} раундів
                    </td>
                  </tr>
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
