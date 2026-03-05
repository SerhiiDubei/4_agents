import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { CoreParameters, Archetype } from '../types/game';
import { GlitchText } from './GlitchText';
import { TypewriterText } from './TypewriterText';
interface RevealViewProps {
  parameters: CoreParameters;
  archetype: Archetype;
  sessionId?: string;
}

type CompileStatus = 'idle' | 'loading' | 'done' | 'error';
const getLabel = (value: number) => {
  if (value < 35) return 'НИЗЬКИЙ';
  if (value < 65) return 'СЕРЕДНІЙ';
  return 'ВИСОКИЙ';
};
const StatBar = ({
  label,
  value,
  delay




}: {label: string;value: number;delay: number;}) => {
  const textLabel = getLabel(value);
  const colorClass =
  value > 65 ? 'bg-game-pink' : value < 35 ? 'bg-game-cyan' : 'bg-game-gold';
  return (
    <motion.div
      initial={{
        opacity: 0,
        x: -20
      }}
      animate={{
        opacity: 1,
        x: 0
      }}
      transition={{
        delay,
        duration: 0.5
      }}
      className="mb-6">

      <div className="flex justify-between font-pixel text-xs md:text-sm text-game-lightGray mb-2">
        <span>{label}</span>
        <span
          className={
          value > 65 ?
          'text-game-pink' :
          value < 35 ?
          'text-game-cyan' :
          'text-game-gold'
          }>

          [{textLabel}]
        </span>
      </div>
      <div className="h-2 w-full bg-game-gray rounded-full overflow-hidden border border-game-lightGray/20">
        <motion.div
          initial={{
            width: 0
          }}
          animate={{
            width: `${value}%`
          }}
          transition={{
            delay: delay + 0.2,
            duration: 1,
            ease: 'easeOut'
          }}
          className={`h-full ${colorClass} shadow-[0_0_10px_currentColor]`} />

      </div>
    </motion.div>);

};
export const RevealView: React.FC<RevealViewProps> = ({
  parameters,
  archetype,
  sessionId: _sessionId,
}) => {
  const [showStats, setShowStats] = useState(false);
  const [compileStatus, setCompileStatus] = useState<CompileStatus>('idle');
  const [soulMd, setSoulMd] = useState('');
  const [agentId, setAgentId] = useState('');
  const [showSoul, setShowSoul] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setShowStats(true), 3500);
    return () => clearTimeout(timer);
  }, []);

  const handleStartSimulation = async () => {
    setCompileStatus('loading');
    try {
      const payload = {
        cooperation_bias: Math.round(parameters.cooperationBias),
        deception_tendency: Math.round(parameters.deceptionTendency),
        strategic_horizon: Math.round(parameters.strategicHorizon),
        risk_appetite: Math.round(parameters.riskAppetite),
        archetype_name: archetype.name,
      };

      const hasSession = Boolean(_sessionId);
      const url = hasSession ? '/compile-from-session' : '/compile-from-params';
      const body = hasSession
        ? JSON.stringify({ session_id: _sessionId, ...payload })
        : JSON.stringify(payload);

      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body,
      });
      if (!res.ok) throw new Error('Server error');
      const data = await res.json();
      setSoulMd(data.soul_md);
      setAgentId(data.agent_id);
      setCompileStatus('done');
      setTimeout(() => setShowSoul(true), 400);
    } catch {
      setCompileStatus('error');
    }
  };
  return (
    <>
      <div className="flex flex-col items-center justify-center min-h-screen p-4 md:p-8 relative z-10 bg-game-black">
        <motion.div
          initial={{
            opacity: 0,
            scale: 0.9
          }}
          animate={{
            opacity: 1,
            scale: 1
          }}
          transition={{
            duration: 1
          }}
          className="w-full max-w-4xl flex flex-col items-center">

          <div className="text-center mb-12">
            <motion.div
              initial={{
                opacity: 0,
                y: -20
              }}
              animate={{
                opacity: 1,
                y: 0
              }}
              className="font-pixel text-game-cyan text-sm mb-4 tracking-widest text-glow-cyan">

              АНАЛІЗ ЗАВЕРШЕНО
            </motion.div>

            <GlitchText
              text={archetype.name}
              className="text-5xl md:text-7xl lg:text-8xl text-white mb-8" />


            <div className="max-w-2xl mx-auto min-h-[100px]">
              <TypewriterText
                text={archetype.description}
                className="font-dialog text-2xl md:text-3xl text-game-lightGray leading-relaxed"
                speed={30} />

            </div>
          </div>

          {showStats &&
          <motion.div
            initial={{
              opacity: 0,
              y: 20
            }}
            animate={{
              opacity: 1,
              y: 0
            }}
            className="w-full max-w-xl bg-game-darkPurple/60 border border-game-pink/50 p-8 rounded-sm box-glow-pink backdrop-blur-md">

              <h3 className="font-pixel text-game-pink text-sm mb-8 text-center tracking-widest">
                ПРОФІЛЬ ПОВЕДІНКИ
              </h3>

              <StatBar
              label="КООПЕРАЦІЯ"
              value={parameters.cooperationBias}
              delay={0.2} />

              <StatBar
              label="СХИЛЬНІСТЬ ДО ОБМАНУ"
              value={parameters.deceptionTendency}
              delay={0.4} />

              <StatBar
              label="СТРАТЕГІЧНЕ МИСЛЕННЯ"
              value={parameters.strategicHorizon}
              delay={0.6} />

              <StatBar
              label="РИЗИКОВАНІСТЬ"
              value={parameters.riskAppetite}
              delay={0.8} />


              <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 2 }}
              className="mt-12 text-center">

                {compileStatus === 'idle' && (
                  <button
                    onClick={handleStartSimulation}
                    className="font-pixel text-game-cyan border border-game-cyan px-8 py-4 hover:bg-game-cyan/10 transition-colors text-sm tracking-widest box-glow-cyan hover:shadow-[0_0_20px_rgba(0,240,255,0.5)]">
                    [ ПОЧАТИ СИМУЛЯЦІЮ ]
                  </button>
                )}

                {compileStatus === 'loading' && (
                  <div className="font-pixel text-game-gold text-xs tracking-widest animate-pulse">
                    ГЕНЕРАЦІЯ АГЕНТА...
                  </div>
                )}

                {compileStatus === 'error' && (
                  <div className="font-pixel text-game-red text-xs tracking-widest">
                    ПОМИЛКА СЕРВЕРА. ПЕРЕВІРТЕ ПІДКЛЮЧЕННЯ.
                  </div>
                )}
              </motion.div>
            </motion.div>
          }
        </motion.div>
      </div>
      {showSoul && soulMd && (
        <motion.div
          initial={{ opacity: 0, y: 40 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8 }}
          className="fixed inset-0 bg-game-black/95 backdrop-blur-md z-50 flex flex-col items-center justify-start p-6 md:p-12 overflow-y-auto">

          <div className="w-full max-w-3xl">
            <div className="font-pixel text-game-cyan text-xs tracking-widest mb-2 text-glow-cyan">
              АГЕНТ ІНІЦІАЛІЗОВАНО
            </div>
            <div className="font-pixel text-game-pink text-sm mb-8 tracking-widest">
              ID: {agentId}
            </div>

            <pre className="font-dialog text-xl text-game-lightGray leading-relaxed whitespace-pre-wrap bg-game-darkPurple/60 border border-game-cyan/30 p-6 rounded-sm mb-8">
              {soulMd}
            </pre>

            <button
              onClick={() => setShowSoul(false)}
              className="font-pixel text-game-pink border border-game-pink px-8 py-4 hover:bg-game-pink/10 transition-colors text-sm tracking-widest">
              [ ЗАКРИТИ ]
            </button>
          </div>
        </motion.div>
      )}
    </>);

};