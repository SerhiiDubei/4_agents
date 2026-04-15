import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';

interface AgentAnalytics {
  name: string;
  games_played: number;
  games_won: number;
  win_rate: number;
  betrayals_committed: number;
  betrayals_received: number;
  mutual_coops: number;
  mutual_defects: number;
  coop_rate: number;
  betrayal_rate: number;
}

interface AnalyticsResponse {
  agents: AgentAnalytics[];
  totals: {
    games: number;
    betrayals: number;
    mutual_coops: number;
  };
}

type SortKey = 'win_rate' | 'betrayal_rate' | 'coop_rate' | 'games_played' | 'betrayals_committed';

const SORT_LABELS: Record<SortKey, string> = {
  win_rate: 'WIN RATE',
  betrayal_rate: 'ЗРАДИ %',
  coop_rate: 'КООПЕР %',
  games_played: 'ІГОР',
  betrayals_committed: 'ВСЬОГО ЗРАД',
};

function StatBar({ value, color, max = 100 }: { value: number; color: string; max?: number }) {
  const pct = Math.min(100, (value / max) * 100);
  return (
    <div className="relative w-full h-1.5 bg-game-gray/30 rounded-full overflow-hidden">
      <motion.div
        initial={{ width: 0 }}
        animate={{ width: `${pct}%` }}
        transition={{ duration: 0.6, ease: 'easeOut' }}
        className={`h-full rounded-full ${color}`}
      />
    </div>
  );
}

export const AnalyticsDashboardView: React.FC<{ onBack?: () => void }> = ({ onBack }) => {
  const [data, setData] = useState<AnalyticsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>('win_rate');
  const [sortDesc, setSortDesc] = useState(true);

  useEffect(() => {
    fetch('/api/analytics/island')
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(res.statusText))))
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-game-black relative z-10">
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="font-pixel text-game-cyan text-sm tracking-widest text-glow-cyan"
        >
          АНАЛІЗ ДАНИХ...
        </motion.div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen p-8 bg-game-black relative z-10">
        <p className="font-pixel text-game-red text-sm">{error || 'Немає даних'}</p>
        {onBack && (
          <button
            onClick={onBack}
            className="mt-6 font-pixel text-game-cyan border border-game-cyan px-6 py-3 text-sm tracking-widest"
          >
            [ НАЗАД ]
          </button>
        )}
      </div>
    );
  }

  const sorted = [...data.agents].sort((a, b) => {
    const va = a[sortKey] as number;
    const vb = b[sortKey] as number;
    return sortDesc ? vb - va : va - vb;
  });

  const handleSort = (key: SortKey) => {
    if (key === sortKey) setSortDesc((d) => !d);
    else { setSortKey(key); setSortDesc(true); }
  };

  const { totals } = data;
  const totalBetrayalRate = totals.games > 0
    ? Math.round((totals.betrayals / Math.max(1, totals.betrayals + totals.mutual_coops)) * 100)
    : 0;

  return (
    <div className="h-screen flex flex-col overflow-hidden bg-game-black relative z-10">
      <div className="flex-1 overflow-y-auto">
        <div className="flex flex-col items-center p-4 md:p-8 pb-12 min-h-full">
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            className="w-full max-w-6xl"
          >
            {/* Заголовок */}
            <div className="text-center mb-8">
              <h1 className="font-pixel text-game-cyan text-sm md:text-base tracking-widest text-glow-cyan mb-2">
                АНАЛІТИКА ПОВЕДІНКИ АГЕНТІВ
              </h1>
              <p className="font-dialog text-game-lightGray text-sm">
                {totals.games} ігор · {totals.betrayals} зрад · {totals.mutual_coops} взаємних кооперацій
              </p>
            </div>

            {/* Загальні метрики */}
            <div className="grid grid-cols-3 gap-4 mb-8">
              {[
                { label: 'ВСЬОГО ІГОР', value: totals.games, color: 'text-game-cyan' },
                { label: 'ЗРАД', value: totals.betrayals, color: 'text-game-red' },
                { label: 'КООПЕР', value: totals.mutual_coops, color: 'text-game-green' },
              ].map(({ label, value, color }) => (
                <motion.div
                  key={label}
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  className="bg-game-darkPurple/40 border border-game-cyan/30 rounded-sm p-4 text-center"
                >
                  <div className={`font-pixel text-xl md:text-2xl ${color} text-glow-cyan`}>{value}</div>
                  <div className="font-pixel text-game-lightGray text-xs mt-1 tracking-widest">{label}</div>
                </motion.div>
              ))}
            </div>

            {/* Рейтинг зрадливості по всіх іграх */}
            <div className="mb-6 bg-game-darkPurple/20 border border-game-red/30 rounded-sm p-4">
              <div className="flex justify-between items-center mb-2">
                <span className="font-pixel text-game-red text-xs tracking-widest">ЗАГАЛЬНИЙ РІВЕНЬ ЗРАДИ</span>
                <span className="font-pixel text-game-red text-sm">{totalBetrayalRate}%</span>
              </div>
              <StatBar value={totalBetrayalRate} color="bg-game-red" />
            </div>

            {/* Сортування */}
            <div className="flex gap-2 flex-wrap mb-4">
              <span className="font-pixel text-game-lightGray text-xs self-center tracking-widest">СОРТУВАТИ:</span>
              {(Object.keys(SORT_LABELS) as SortKey[]).map((key) => (
                <button
                  key={key}
                  onClick={() => handleSort(key)}
                  className={`font-pixel text-xs px-3 py-1 border tracking-widest transition-colors ${
                    sortKey === key
                      ? 'border-game-cyan text-game-cyan bg-game-cyan/10'
                      : 'border-game-gray/50 text-game-lightGray hover:border-game-cyan/50'
                  }`}
                >
                  {SORT_LABELS[key]}{sortKey === key ? (sortDesc ? ' ↓' : ' ↑') : ''}
                </button>
              ))}
            </div>

            {/* Таблиця агентів */}
            <div className="space-y-2">
              {sorted.map((agent, idx) => (
                <motion.div
                  key={agent.name}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: idx * 0.03 }}
                  className="bg-game-darkPurple/40 border border-game-cyan/20 rounded-sm p-4 hover:border-game-cyan/50 transition-colors"
                >
                  <div className="flex flex-col md:flex-row md:items-center gap-3">
                    {/* Ім'я та базові метрики */}
                    <div className="flex-shrink-0 w-full md:w-40">
                      <div className="font-dialog text-game-cyan font-bold text-sm">{agent.name}</div>
                      <div className="font-pixel text-game-lightGray text-xs mt-0.5">
                        {agent.games_played} ігор · {agent.games_won} перемог
                      </div>
                    </div>

                    {/* Метрики з барами */}
                    <div className="flex-1 grid grid-cols-1 md:grid-cols-3 gap-3">
                      {/* Win rate */}
                      <div>
                        <div className="flex justify-between mb-1">
                          <span className="font-pixel text-game-gold text-xs tracking-widest">WIN RATE</span>
                          <span className="font-pixel text-game-gold text-xs">{agent.win_rate}%</span>
                        </div>
                        <StatBar value={agent.win_rate} color="bg-game-gold" />
                      </div>

                      {/* Cooperation rate */}
                      <div>
                        <div className="flex justify-between mb-1">
                          <span className="font-pixel text-game-green text-xs tracking-widest">КООП</span>
                          <span className="font-pixel text-game-green text-xs">{agent.coop_rate}%</span>
                        </div>
                        <StatBar value={agent.coop_rate} color="bg-green-500" />
                      </div>

                      {/* Betrayal rate */}
                      <div>
                        <div className="flex justify-between mb-1">
                          <span className="font-pixel text-game-red text-xs tracking-widest">ЗРАДИ</span>
                          <span className="font-pixel text-game-red text-xs">{agent.betrayal_rate}%</span>
                        </div>
                        <StatBar value={agent.betrayal_rate} color="bg-game-red" />
                      </div>
                    </div>

                    {/* Числові деталі */}
                    <div className="flex-shrink-0 grid grid-cols-2 gap-x-4 gap-y-1 text-right md:text-right">
                      <div>
                        <div className="font-pixel text-game-red text-xs">{agent.betrayals_committed}</div>
                        <div className="font-pixel text-game-lightGray text-xs opacity-60">скоєно зрад</div>
                      </div>
                      <div>
                        <div className="font-pixel text-game-pink text-xs">{agent.betrayals_received}</div>
                        <div className="font-pixel text-game-lightGray text-xs opacity-60">зраджений</div>
                      </div>
                      <div>
                        <div className="font-pixel text-game-green text-xs">{agent.mutual_coops}</div>
                        <div className="font-pixel text-game-lightGray text-xs opacity-60">взаємн кооп</div>
                      </div>
                      <div>
                        <div className="font-pixel text-game-gray text-xs">{agent.mutual_defects}</div>
                        <div className="font-pixel text-game-lightGray text-xs opacity-60">взаємн зрад</div>
                      </div>
                    </div>
                  </div>
                </motion.div>
              ))}
            </div>
          </motion.div>
        </div>
      </div>

      {/* Навігація */}
      {onBack && (
        <div className="flex-shrink-0 p-4 border-t border-game-cyan/20 bg-game-black/80 backdrop-blur-sm flex justify-center">
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={onBack}
            className="font-pixel text-game-cyan border border-game-cyan px-8 py-3 text-xs tracking-widest box-glow-cyan"
          >
            [ НАЗАД ]
          </motion.button>
        </div>
      )}
    </div>
  );
};
