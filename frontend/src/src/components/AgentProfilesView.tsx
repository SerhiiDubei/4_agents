import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';

interface CoreParams {
  cooperation_bias: number;
  deception_tendency: number;
  strategic_horizon: number;
  risk_appetite: number;
}

interface AgentProfile {
  id: string;
  name: string;
  role: string;
  roleLabel: string;
  roleColor: 'red' | 'pink' | 'cyan' | 'gold';
  core: CoreParams;
  profession: string;
  bio: string;
  connections: string;
}

interface RosterProfilesResponse {
  profiles: AgentProfile[];
  count: number;
}

const ROLE_COLOR_CLASSES: Record<string, string> = {
  red:  'text-game-red border-game-red/70',
  pink: 'text-game-pink border-game-pink/70',
  cyan: 'text-game-cyan border-game-cyan/70',
  gold: 'text-game-gold border-game-gold/70',
};

const PARAM_LABELS: Record<keyof CoreParams, string> = {
  cooperation_bias:   'КООПЕР',
  deception_tendency: 'ОБМАН',
  strategic_horizon:  'СТРАТЕГ',
  risk_appetite:      'РИЗИК',
};

const PARAM_COLOR: Record<keyof CoreParams, string> = {
  cooperation_bias:   'bg-emerald-400',
  deception_tendency: 'bg-red-400',
  strategic_horizon:  'bg-blue-400',
  risk_appetite:      'bg-yellow-400',
};

/** Смуга прогресу для одного CORE параметру */
const CoreBar: React.FC<{ label: string; value: number; colorClass: string }> = ({ label, value, colorClass }) => (
  <div className="mb-1.5">
    <div className="flex justify-between items-center mb-0.5">
      <span className="font-pixel text-[9px] text-game-lightGray/80 tracking-widest">{label}</span>
      <span className="font-pixel text-[9px] text-game-lightGray/60 tabular-nums">{value}</span>
    </div>
    <div className="h-1.5 w-full bg-game-gray/30 rounded-sm overflow-hidden">
      <motion.div
        className={`h-full rounded-sm ${colorClass}`}
        initial={{ width: 0 }}
        animate={{ width: `${value}%` }}
        transition={{ duration: 0.6, ease: 'easeOut' }}
      />
    </div>
  </div>
);

/** Картка одного агента */
const AgentCard: React.FC<{ profile: AgentProfile; index: number; onClick: () => void }> = ({ profile, index, onClick }) => {
  const colorClass = ROLE_COLOR_CLASSES[profile.roleColor] || ROLE_COLOR_CLASSES.cyan;

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.04 }}
      whileHover={{ scale: 1.02, boxShadow: '0 0 20px rgba(0,240,255,0.15)' }}
      onClick={onClick}
      className="cursor-pointer border border-game-gray/40 hover:border-game-cyan/40 bg-game-darkPurple/50 p-4 rounded-sm backdrop-blur-sm transition-colors"
    >
      {/* Заголовок: ім'я + бейдж ролі */}
      <div className="flex items-start justify-between gap-2 mb-3">
        <h3 className="font-dialog text-white text-base font-bold leading-tight">{profile.name}</h3>
        <span className={`font-pixel text-[9px] border px-1.5 py-0.5 tracking-widest shrink-0 ${colorClass}`}>
          {profile.roleLabel.toUpperCase()}
        </span>
      </div>

      {/* Професія */}
      {profile.profession && (
        <p className="font-dialog text-game-lightGray/60 text-xs mb-3 italic">{profile.profession}</p>
      )}

      {/* CORE параметри */}
      <div className="mb-3">
        {(Object.keys(PARAM_LABELS) as (keyof CoreParams)[]).map((param) => (
          <CoreBar
            key={param}
            label={PARAM_LABELS[param]}
            value={profile.core[param]}
            colorClass={PARAM_COLOR[param]}
          />
        ))}
      </div>

      {/* Bio-витяг */}
      {profile.bio && (
        <p className="font-dialog text-game-lightGray/70 text-xs leading-relaxed line-clamp-3">
          {profile.bio}
        </p>
      )}
    </motion.div>
  );
};

/** Детальна панель агента (розгортається знизу при кліку) */
const AgentDetailPanel: React.FC<{ profile: AgentProfile; onClose: () => void }> = ({ profile, onClose }) => {
  const colorClass = ROLE_COLOR_CLASSES[profile.roleColor] || ROLE_COLOR_CLASSES.cyan;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 20 }}
      className="fixed inset-0 z-50 flex items-end md:items-center justify-center p-4 bg-game-black/80 backdrop-blur-sm"
      onClick={onClose}
    >
      <motion.div
        className="w-full max-w-lg border border-game-cyan/50 bg-game-darkPurple/95 p-6 rounded-sm box-glow-cyan"
        onClick={(e) => e.stopPropagation()}
        initial={{ scale: 0.95 }}
        animate={{ scale: 1 }}
      >
        {/* Заголовок */}
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="font-dialog text-white text-xl font-bold">{profile.name}</h2>
            <span className={`font-pixel text-[10px] border px-2 py-0.5 mt-1 inline-block tracking-widest ${colorClass}`}>
              {profile.roleLabel.toUpperCase()}
            </span>
          </div>
          <button
            onClick={onClose}
            className="font-pixel text-game-lightGray/60 text-xs hover:text-game-red transition-colors"
          >
            [ X ]
          </button>
        </div>

        {/* Професія */}
        {profile.profession && (
          <p className="font-dialog text-game-lightGray/70 text-sm italic mb-4">{profile.profession}</p>
        )}

        {/* CORE bars — більші */}
        <div className="mb-4 border border-game-gray/30 bg-game-black/30 p-3 rounded-sm">
          <p className="font-pixel text-[9px] text-game-cyan tracking-widest mb-2">CORE ПАРАМЕТРИ</p>
          {(Object.keys(PARAM_LABELS) as (keyof CoreParams)[]).map((param) => (
            <div key={param} className="mb-2">
              <div className="flex justify-between items-center mb-1">
                <span className="font-pixel text-[10px] text-game-lightGray tracking-widest">{PARAM_LABELS[param]}</span>
                <span className="font-pixel text-[10px] text-game-gold tabular-nums">{profile.core[param]}/100</span>
              </div>
              <div className="h-2 w-full bg-game-gray/30 rounded-sm overflow-hidden">
                <motion.div
                  className={`h-full rounded-sm ${PARAM_COLOR[param]}`}
                  initial={{ width: 0 }}
                  animate={{ width: `${profile.core[param]}%` }}
                  transition={{ duration: 0.8, ease: 'easeOut' }}
                />
              </div>
            </div>
          ))}
        </div>

        {/* Bio */}
        {profile.bio && (
          <div className="mb-4">
            <p className="font-pixel text-[9px] text-game-cyan tracking-widest mb-2">БІОГРАФІЯ</p>
            <p className="font-dialog text-game-lightGray/80 text-sm leading-relaxed">{profile.bio}</p>
          </div>
        )}

        {/* Зв'язки */}
        {profile.connections && (
          <div>
            <p className="font-pixel text-[9px] text-game-cyan tracking-widest mb-2">ЗВ'ЯЗКИ</p>
            <p className="font-dialog text-game-lightGray/70 text-xs leading-relaxed">{profile.connections}</p>
          </div>
        )}
      </motion.div>
    </motion.div>
  );
};

/** Головний view — сітка профілів агентів */
export const AgentProfilesView: React.FC<{ onBack?: () => void }> = ({ onBack }) => {
  const [data, setData] = useState<RosterProfilesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<AgentProfile | null>(null);
  const [filterRole, setFilterRole] = useState<string>('all');

  useEffect(() => {
    fetch('/api/roster/profiles')
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
          ЗАВАНТАЖЕННЯ ПРОФІЛІВ...
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

  const roles = ['all', 'role_snake', 'role_gambler', 'role_banker', 'role_peacekeeper'];
  const roleFilterLabels: Record<string, string> = {
    all: 'ВСІ',
    role_snake: 'ЗМІЯ',
    role_gambler: 'ГРАВЕЦЬ',
    role_banker: 'БАНКІР',
    role_peacekeeper: 'МИРОТВОРЕЦЬ',
  };
  const filtered = filterRole === 'all'
    ? data.profiles
    : data.profiles.filter((p) => p.role === filterRole);

  return (
    <div className="h-screen flex flex-col overflow-hidden bg-game-black relative z-10">
      {/* Деталі-панель */}
      {selected && (
        <AgentDetailPanel profile={selected} onClose={() => setSelected(null)} />
      )}

      <div className="flex-1 overflow-y-auto">
        <div className="flex flex-col items-center p-4 md:p-8 pb-12 min-h-full">
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            className="w-full max-w-6xl"
          >
            {/* Заголовок */}
            <div className="text-center mb-6">
              <h1 className="font-pixel text-game-cyan text-sm md:text-base tracking-widest text-glow-cyan mb-2">
                ПРОФІЛІ АГЕНТІВ
              </h1>
              <p className="font-dialog text-game-lightGray text-lg">
                {data.count} агентів · CORE параметри · ролі · біографії
              </p>
            </div>

            {/* Фільтр за роллю */}
            <div className="flex flex-wrap gap-2 justify-center mb-6">
              {roles.map((role) => (
                <button
                  key={role}
                  onClick={() => setFilterRole(role)}
                  className={`font-pixel text-[10px] px-3 py-1.5 border tracking-widest transition-colors ${
                    filterRole === role
                      ? 'border-game-cyan text-game-cyan bg-game-cyan/10'
                      : 'border-game-gray/50 text-game-lightGray/60 hover:border-game-cyan/40 hover:text-game-cyan/70'
                  }`}
                >
                  {roleFilterLabels[role]}
                </button>
              ))}
            </div>

            {/* Сітка карток */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
              {filtered.map((profile, idx) => (
                <AgentCard
                  key={profile.id}
                  profile={profile}
                  index={idx}
                  onClick={() => setSelected(profile)}
                />
              ))}
            </div>

            {filtered.length === 0 && (
              <div className="text-center py-16">
                <p className="font-pixel text-game-lightGray/50 text-sm">Немає агентів у цій ролі</p>
              </div>
            )}

            {/* Кнопка назад */}
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
