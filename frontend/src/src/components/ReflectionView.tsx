import React, { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Reflection } from '../types/game';
import { TypewriterText } from './TypewriterText';

interface ReflectionViewProps {
  reflection: Reflection;
  onContinue: () => void;
}

export const ReflectionView: React.FC<ReflectionViewProps> = ({
  reflection,
  onContinue,
}) => {
  const [showContinue, setShowContinue] = useState(false);

  useEffect(() => {
    setShowContinue(false);
  }, [reflection.id]);

  return (
    <div className="flex flex-col items-center justify-center min-h-screen p-8 text-center relative z-10">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm pointer-events-none"></div>

      <div className="max-w-2xl w-full space-y-16 relative z-10">
        <motion.div
          initial={{
            opacity: 0,
            scale: 0.9,
          }}
          animate={{
            opacity: 1,
            scale: 1,
          }}
          transition={{
            duration: 1,
          }}
          className="min-h-[150px] italic"
        >
          <TypewriterText
            text={`"${reflection.text}"`}
            className="font-dialog text-3xl md:text-4xl text-game-gold text-glow-gold leading-relaxed"
            speed={40}
            onComplete={() => setTimeout(() => setShowContinue(true), 1000)}
          />
        </motion.div>

        <AnimatePresence>
          {showContinue && (
            <motion.button
              initial={{
                opacity: 0,
              }}
              animate={{
                opacity: 1,
              }}
              exit={{
                opacity: 0,
              }}
              whileHover={{
                scale: 1.05,
                color: '#fff',
              }}
              whileTap={{
                scale: 0.95,
              }}
              onClick={onContinue}
              className="font-pixel text-sm text-game-lightGray uppercase tracking-widest transition-colors duration-300"
            >
              [ ПРОДОВЖИТИ ]
            </motion.button>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
};
