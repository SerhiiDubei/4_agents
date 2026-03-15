import React, { useState } from 'react';
import { motion } from 'framer-motion';

interface InitResultViewProps {
  agentId: string;
  soulMd: string;
  core: Record<string, number>;
  onReset?: () => void;
}

const getLabel = (value: number) => {
  if (value < 35) return 'НИЗЬКИЙ';
  if (value < 65) return 'СЕРЕДНІЙ';
  return 'ВИСОКИЙ';
};

const StatBar = ({ label, value }: { label: string; value: number }) => {
  const textLabel = getLabel(value);
  const colorClass =
    value > 65 ? 'bg-game-pink' : value < 35 ? 'bg-game-cyan' : 'bg-game-gold';
  return (
    <motion.div
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.5 }}
      className="mb-6"
    >
      <div className="flex justify-between font-pixel text-xs md:text-sm text-game-lightGray mb-2">
        <span>{label}</span>
        <span
          className={
            value > 65 ? 'text-game-pink' : value < 35 ? 'text-game-cyan' : 'text-game-gold'
          }
        >
          [{textLabel}]
        </span>
      </div>
      <div className="h-2 w-full bg-game-gray rounded-full overflow-hidden border border-game-lightGray/20">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${value}%` }}
          transition={{ duration: 1, ease: 'easeOut' }}
          className={`h-full ${colorClass} shadow-[0_0_10px_currentColor]`}
        />
      </div>
    </motion.div>
  );
};

export const InitResultView: React.FC<InitResultViewProps> = ({
  agentId,
  soulMd,
  core,
  onReset,
}) => {
  const [showSoul, setShowSoul] = useState(false);

  const coreLabels: Record<string, string> = {
    cooperation_bias: 'КООПЕРАЦІЯ',
    deception_tendency: 'СХИЛЬНІСТЬ ДО ОБМАНУ',
    strategic_horizon: 'СТРАТЕГІЧНЕ МИСЛЕННЯ',
    risk_appetite: 'РИЗИКОВАНІСТЬ',
  };

  return (
    <div className="flex flex-col items-center justify-center min-h-screen p-4 md:p-8 relative z-10 bg-game-black">
      <motion.div
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 1 }}
        className="w-full max-w-4xl flex flex-col items-center"
      >
        <div className="text-center mb-12">
          <motion.div
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            className="font-pixel text-game-cyan text-sm mb-4 tracking-widest text-glow-cyan"
          >
            ПЕРСОНАЖ СТВОРЕНО
          </motion.div>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.3 }}
            className="font-pixel text-game-pink text-sm mb-8 tracking-widest"
          >
            ID: {agentId}
          </motion.div>
        </div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.5 }}
          className="w-full max-w-xl bg-game-darkPurple/60 border border-game-pink/50 p-8 rounded-sm box-glow-pink backdrop-blur-md mb-8"
        >
          <h3 className="font-pixel text-game-pink text-sm mb-8 text-center tracking-widest">
            ПРОФІЛЬ ПОВЕДІНКИ
          </h3>
          {Object.entries(coreLabels).map(([key, label], i) => (
            <StatBar
              key={key}
              label={label}
              value={core[key] ?? 50}
            />
          ))}
        </motion.div>

        <div className="flex gap-4">
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={() => setShowSoul(true)}
            className="font-pixel text-game-cyan border border-game-cyan px-8 py-4 hover:bg-game-cyan/10 transition-colors text-sm tracking-widest box-glow-cyan"
          >
            [ ПЕРЕГЛЯНУТИ SOUL ]
          </motion.button>
          {onReset && (
            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              onClick={onReset}
              className="font-pixel text-game-lightGray border border-game-lightGray/50 px-8 py-4 hover:bg-game-lightGray/10 transition-colors text-sm tracking-widest"
            >
              [ СТВОРИТИ ЩЕ ]
            </motion.button>
          )}
        </div>
      </motion.div>

      {showSoul && soulMd && (
        <motion.div
          initial={{ opacity: 0, y: 40 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8 }}
          className="fixed inset-0 bg-game-black/95 backdrop-blur-md z-50 flex flex-col items-center justify-start p-6 md:p-12 overflow-y-auto"
        >
          <div className="w-full max-w-3xl">
            <div className="font-pixel text-game-cyan text-xs tracking-widest mb-2 text-glow-cyan">
              SOUL.md
            </div>
            <div className="font-pixel text-game-pink text-sm mb-8 tracking-widest">
              {agentId}
            </div>
            <pre className="font-dialog text-xl text-game-lightGray leading-relaxed whitespace-pre-wrap bg-game-darkPurple/60 border border-game-cyan/30 p-6 rounded-sm mb-8">
              {soulMd}
            </pre>
            <button
              onClick={() => setShowSoul(false)}
              className="font-pixel text-game-pink border border-game-pink px-8 py-4 hover:bg-game-pink/10 transition-colors text-sm tracking-widest"
            >
              [ ЗАКРИТИ ]
            </button>
          </div>
        </motion.div>
      )}
    </div>
  );
};
